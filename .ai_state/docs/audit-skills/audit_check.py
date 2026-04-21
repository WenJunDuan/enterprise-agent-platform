#!/usr/bin/env python3
"""
出差报销审计引擎 v2.0
======================
20 类检查 × 5 个维度，覆盖时间/金额/职级/票据/逻辑一致性

输入: extracted_expenses.json + rules.yaml
输出: audit_results.json

用法:
    python audit_check.py \
        --expenses /home/claude/extracted_expenses.json \
        --rules /path/to/rules.yaml \
        --output /home/claude/audit_results.json
"""

import json
import sys
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

try:
    import yaml
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml",
                           "--break-system-packages", "-q"])
    import yaml


# =============================================================================
# 工具函数
# =============================================================================

def load_json(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def parse_date(d) -> datetime | None:
    if not d:
        return None
    if isinstance(d, datetime):
        return d
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(str(d).strip(), fmt)
        except ValueError:
            continue
    return None

def get_city_tier(city: str, city_tiers: dict) -> str:
    if not city:
        return "tier_3"
    for tier_key, tier_data in city_tiers.items():
        if city in tier_data.get("cities", []):
            return tier_key
    return "tier_3"

def get_limit(matrix, rank_tier: str, city_tier: str):
    """从限额矩阵取值。支持 scalar / dict-of-scalar / dict-of-dict。"""
    if isinstance(matrix, (int, float)):
        return matrix
    tier_data = matrix.get(rank_tier, matrix.get("staff", {}))
    if isinstance(tier_data, (int, float)):
        return tier_data
    return tier_data.get(city_tier, tier_data.get("tier_3", 0))

def get_rank(expense: dict, default: str) -> str:
    """从费用记录或全局默认取职级。"""
    return expense.get("rank_tier") or default

def is_weekend(dt: datetime) -> bool:
    return dt.weekday() >= 5  # 5=Saturday, 6=Sunday

def is_holiday(dt: datetime, holidays: dict) -> str | None:
    """检查是否为固定节假日。返回假日名或None。"""
    for h in holidays.get("fixed", []):
        days = h.get("days", [h.get("day")])
        if dt.month == h["month"] and dt.day in days:
            return h["name"]
    return None

def class_rank(cls: str | None, hierarchy: list[str]) -> int:
    """返回等级在层级表中的位置，越高越大。未知返回 -1。"""
    if not cls:
        return -1
    cls_lower = cls.lower().strip()
    for i, h in enumerate(hierarchy):
        if h.lower() == cls_lower:
            return i
    return -1


# =============================================================================
# 审计结果容器
# =============================================================================

class AuditResult:
    def __init__(self):
        self.findings = []
        self.summary = {"pass": 0, "warning": 0, "fail": 0, "unknown": 0}

    def add(self, status: str, rule_id: str, description: str,
            detail: str, source_files: list[str] | None = None,
            severity: str = "MEDIUM"):
        self.findings.append({
            "status": status,
            "rule_id": rule_id,
            "description": description,
            "detail": detail,
            "source_files": source_files or [],
            "severity": severity
        })
        self.summary[status] = self.summary.get(status, 0) + 1

    def to_dict(self) -> dict:
        return {"summary": self.summary, "findings": self.findings}


# =============================================================================
# 上下文：从费用数据中提取出差全局信息
# =============================================================================

class TripContext:
    """从费用记录集合中推导出差上下文信息"""
    def __init__(self, expenses: list[dict], rules: dict):
        self.expenses = expenses
        self.rules = rules
        self.default_tier = rules.get("default_tier", "staff")
        self.city_tiers = rules.get("city_tiers", {})
        self.thresholds = rules.get("thresholds", {})

        # 推导出差日期范围
        self.trip_start = None
        self.trip_end = None
        self.trip_days = 0
        self._compute_trip_dates()

        # 推导目的地
        self.destinations = set()
        self.departure_cities = set()
        self._compute_locations()

        # 推导职级
        self.rank_tier = self._compute_rank()

        # 推导报销总额和提交日期
        self.total_amount = self._compute_total()
        self.submission_date = self._compute_submission_date()

    def _compute_trip_dates(self):
        starts, ends = [], []
        for e in self.expenses:
            if e.get("doc_type") == "itinerary":
                dr = e.get("date_range", {})
                s, end = parse_date(dr.get("start")), parse_date(dr.get("end"))
                if s:
                    starts.append(s)
                if end:
                    ends.append(end)
        if starts and ends:
            self.trip_start = min(starts)
            self.trip_end = max(ends)
            self.trip_days = (self.trip_end - self.trip_start).days + 1

    def _compute_locations(self):
        for e in self.expenses:
            if e.get("doc_type") == "itinerary":
                city = (e.get("location") or {}).get("city", "")
                if city:
                    self.destinations.add(city)
                dep = e.get("departure_city", "")
                if dep:
                    self.departure_cities.add(dep)

    def _compute_rank(self) -> str:
        for e in self.expenses:
            r = e.get("rank_tier")
            if r and r != "null":
                return r
        return self.default_tier

    def _compute_total(self) -> float:
        # 优先用报销单金额
        for e in self.expenses:
            if e.get("doc_type") == "expense_report" and e.get("amount"):
                return e["amount"]
        # 否则累加票据
        return sum(e.get("amount", 0) for e in self.expenses
                   if e.get("doc_type") not in ("itinerary", "expense_report")
                   and e.get("amount"))

    def _compute_submission_date(self) -> datetime | None:
        for e in self.expenses:
            if e.get("doc_type") == "expense_report":
                return parse_date(e.get("submission_date"))
        return None

    @property
    def fee_items(self) -> list[dict]:
        """非行程单、非报销单的费用项"""
        return [e for e in self.expenses
                if e.get("doc_type") not in ("itinerary", "expense_report")]


# =============================================================================
# ▌ 维度 1: 时间检查 (4项)
# =============================================================================

def check_01_date_in_range(ctx: TripContext, r: AuditResult):
    """GEN-002: 费用日期在出差范围内"""
    if not ctx.trip_start:
        r.add("unknown", "GEN-002", "无行程单/出差审批单",
              "无法确定出差日期范围，跳过时间线检查", severity="HIGH")
        return

    tol = timedelta(days=ctx.thresholds.get("date_tolerance_days", 1))
    for exp in ctx.fee_items:
        exp_date = parse_date(exp.get("date"))
        if not exp_date:
            continue
        if ctx.trip_start - tol <= exp_date <= ctx.trip_end + tol:
            if exp_date < ctx.trip_start or exp_date > ctx.trip_end:
                r.add("warning", "GEN-002", "费用日期在出差范围边界",
                      f"{exp['source_file']}: {exp['date']}，"
                      f"出差期间 {ctx.trip_start.date()}~{ctx.trip_end.date()}",
                      [exp["source_file"]], "MEDIUM")
            else:
                r.add("pass", "GEN-002", "费用日期在出差范围内",
                      f"{exp['source_file']}: {exp['date']}",
                      [exp["source_file"]])
        else:
            delta = min(abs((exp_date - ctx.trip_start).days),
                        abs((exp_date - ctx.trip_end).days))
            r.add("fail", "GEN-002", "费用日期超出出差范围",
                  f"{exp['source_file']}: {exp['date']}，"
                  f"偏离出差期间 {delta} 天",
                  [exp["source_file"]], "HIGH")


def check_02_hotel_nights_vs_trip(ctx: TripContext, r: AuditResult):
    """ACC-004: 住宿天数 ≤ 出差天数 - 1"""
    if not ctx.trip_start or ctx.trip_days <= 0:
        return

    max_nights = max(ctx.trip_days - 1, 0)  # 当天往返=0晚

    hotels = [e for e in ctx.expenses
              if e.get("subcategory") == "hotel" or e.get("doc_type") == "hotel"]

    total_nights = 0
    for h in hotels:
        n = h.get("nights")
        if n is not None:
            total_nights += n
        else:
            ci = parse_date(h.get("check_in") or (h.get("date_range") or {}).get("start"))
            co = parse_date(h.get("check_out") or (h.get("date_range") or {}).get("end"))
            if ci and co and co > ci:
                total_nights += (co - ci).days
            elif h.get("amount"):
                total_nights += 1  # 无法判断，保守计1晚

    if total_nights == 0:
        return

    if total_nights <= max_nights:
        r.add("pass", "ACC-004", "住宿天数合理",
              f"住宿 {total_nights} 晚，出差 {ctx.trip_days} 天（上限 {max_nights} 晚）",
              severity="MEDIUM")
    elif total_nights == max_nights + 1:
        r.add("warning", "ACC-004", "住宿天数略多",
              f"住宿 {total_nights} 晚，出差 {ctx.trip_days} 天（上限 {max_nights} 晚），多 1 晚",
              severity="MEDIUM")
    else:
        r.add("fail", "ACC-004", "住宿天数超出出差天数",
              f"住宿 {total_nights} 晚，出差 {ctx.trip_days} 天（上限 {max_nights} 晚），"
              f"多 {total_nights - max_nights} 晚",
              severity="HIGH")


def check_03_reimbursement_deadline(ctx: TripContext, r: AuditResult):
    """GEN-005: 报销时效"""
    deadline_days = ctx.rules.get("general", {}).get("reimbursement_deadline_days", 30)
    if not ctx.trip_end or not ctx.submission_date:
        r.add("unknown", "GEN-005", "无法判断报销时效",
              "缺少出差结束日期或报销提交日期", severity="LOW")
        return

    elapsed = (ctx.submission_date - ctx.trip_end).days
    if elapsed < 0:
        r.add("warning", "GEN-005", "报销提交日期早于出差结束",
              f"出差结束 {ctx.trip_end.date()}，提交 {ctx.submission_date.date()}",
              severity="MEDIUM")
    elif elapsed <= deadline_days:
        r.add("pass", "GEN-005", "报销时效合规",
              f"出差结束后 {elapsed} 天内提交（上限 {deadline_days} 天）")
    else:
        r.add("fail", "GEN-005", "报销超时",
              f"出差结束后 {elapsed} 天提交，超出 {deadline_days} 天时限",
              severity="MEDIUM")


def check_04_weekend_holiday(ctx: TripContext, r: AuditResult):
    """GEN-009: 周末/节假日费用标记"""
    holidays = ctx.rules.get("holidays", {})
    for exp in ctx.fee_items:
        exp_date = parse_date(exp.get("date"))
        if not exp_date:
            continue
        holiday_name = is_holiday(exp_date, holidays)
        if holiday_name:
            r.add("warning", "GEN-009", f"节假日({holiday_name})产生费用",
                  f"{exp['source_file']}: {exp['date']} 为{holiday_name}，"
                  f"¥{exp.get('amount', 0):.2f} ({exp.get('subcategory', '')})",
                  [exp["source_file"]], "LOW")
        elif is_weekend(exp_date):
            r.add("warning", "GEN-009", "周末产生费用",
                  f"{exp['source_file']}: {exp['date']} 为周末，"
                  f"¥{exp.get('amount', 0):.2f} ({exp.get('subcategory', '')})",
                  [exp["source_file"]], "LOW")


# =============================================================================
# ▌ 维度 2: 金额检查 (5项)
# =============================================================================

def check_05_amount_consistency(ctx: TripContext, r: AuditResult):
    """GEN-001: 报销单总额 vs 票据合计"""
    reports = [e for e in ctx.expenses if e.get("doc_type") == "expense_report"]
    invoices = [e for e in ctx.fee_items if e.get("amount") is not None]

    if not reports:
        r.add("unknown", "GEN-001", "未找到报销单/费用汇总",
              "无法核对汇总金额", severity="MEDIUM")
        return

    for report in reports:
        report_total = report.get("amount", 0)
        invoice_total = sum(e.get("amount", 0) for e in invoices)
        diff = abs(report_total - invoice_total)
        if diff < 0.01:
            r.add("pass", "GEN-001", "报销金额与票据合计一致",
                  f"报销单 ¥{report_total:.2f} = 票据合计 ¥{invoice_total:.2f}",
                  [report.get("source_file", "")])
        else:
            pct = (diff / report_total * 100) if report_total > 0 else 100
            r.add("fail", "GEN-001", "报销金额与票据合计不一致",
                  f"报销单 ¥{report_total:.2f} ≠ 票据合计 ¥{invoice_total:.2f}，"
                  f"差额 ¥{diff:.2f} ({pct:.1f}%)",
                  [report.get("source_file", "")], "HIGH")


def check_06_accommodation_limit(ctx: TripContext, r: AuditResult):
    """ACC-001: 住宿每晚 vs 职级×城市限额"""
    acc = ctx.rules.get("accommodation", {})
    limits = acc.get("daily_limit", {})
    tol_pct = ctx.thresholds.get("amount_tolerance_percent", 10)

    hotels = [e for e in ctx.expenses
              if e.get("subcategory") == "hotel" or e.get("doc_type") == "hotel"]

    for h in hotels:
        city = (h.get("location") or {}).get("city", "")
        c_tier = get_city_tier(city, ctx.city_tiers)
        rank = get_rank(h, ctx.rank_tier)
        limit = get_limit(limits, rank, c_tier)
        if not limit:
            continue

        # 计算每晚均价
        daily_rate = h.get("daily_rate")
        if daily_rate is None:
            amount = h.get("amount", 0)
            nights = h.get("nights")
            if not nights:
                ci = parse_date(h.get("check_in") or (h.get("date_range") or {}).get("start"))
                co = parse_date(h.get("check_out") or (h.get("date_range") or {}).get("end"))
                nights = (co - ci).days if ci and co and co > ci else 1
            daily_rate = amount / nights if nights > 0 else amount

        if daily_rate <= limit:
            r.add("pass", "ACC-001", "住宿费用在标准内",
                  f"{h['source_file']}: ¥{daily_rate:.0f}/晚 "
                  f"(上限 ¥{limit}/晚, {rank}/{city or '未知'} {c_tier})",
                  [h["source_file"]])
        elif daily_rate <= limit * (1 + tol_pct / 100):
            over = (daily_rate / limit - 1) * 100
            r.add("warning", "ACC-001", "住宿费用接近上限",
                  f"{h['source_file']}: ¥{daily_rate:.0f}/晚 "
                  f"(上限 ¥{limit}/晚, 超出 {over:.0f}%)",
                  [h["source_file"]], "MEDIUM")
        else:
            over = (daily_rate / limit - 1) * 100
            r.add("fail", "ACC-001", "住宿费用超标",
                  f"{h['source_file']}: ¥{daily_rate:.0f}/晚 "
                  f"(上限 ¥{limit}/晚, 超出 {over:.0f}%，"
                  f"职级 {rank}, 城市等级 {c_tier})",
                  [h["source_file"]], "HIGH")


def check_07_taxi_daily_limit(ctx: TripContext, r: AuditResult):
    """TRA-X01: 单日出租车累计 vs 日限额"""
    taxi_rules = ctx.rules.get("transportation", {}).get("taxi", {})
    limits = taxi_rules.get("daily_limit", {})
    rank = ctx.rank_tier
    limit = get_limit(limits, rank, "tier_1")  # taxi limit不分城市
    if not limit:
        return

    # 按日期分组出租车费用
    daily_taxi = defaultdict(lambda: {"total": 0.0, "files": []})
    for e in ctx.fee_items:
        if e.get("subcategory") in ("taxi", "rideshare"):
            d = e.get("date", "unknown")
            daily_taxi[d]["total"] += e.get("amount", 0)
            daily_taxi[d]["files"].append(e.get("source_file", ""))

    for date_str, info in daily_taxi.items():
        if info["total"] <= limit:
            r.add("pass", "TRA-X01", "出租车日费用合规",
                  f"{date_str}: ¥{info['total']:.0f} (上限 ¥{limit}/日)",
                  info["files"])
        else:
            over = info['total'] - limit
            r.add("fail", "TRA-X01", "出租车日费用超标",
                  f"{date_str}: ¥{info['total']:.0f} (上限 ¥{limit}/日，"
                  f"超出 ¥{over:.0f}，职级 {rank})",
                  info["files"], "MEDIUM")


def check_08_business_meal_limit(ctx: TripContext, r: AuditResult):
    """MEA-B02: 商务餐人均限额"""
    meal_rules = ctx.rules.get("meals", {}).get("business_meal", {})
    per_person = meal_rules.get("per_person_limit", 0)
    if not per_person:
        return

    meals = [e for e in ctx.fee_items if e.get("subcategory") == "business_meal"]
    for m in meals:
        amount = m.get("amount", 0)
        guest_count = m.get("guest_count")

        if not guest_count:
            r.add("unknown", "MEA-B02", "商务餐缺少用餐人数",
                  f"{m['source_file']}: ¥{amount:.2f}，无法计算人均",
                  [m["source_file"]], "MEDIUM")
            continue

        avg = amount / guest_count
        if avg <= per_person:
            r.add("pass", "MEA-B02", "商务餐人均合规",
                  f"{m['source_file']}: ¥{amount:.0f} / {guest_count}人 = "
                  f"¥{avg:.0f}/人 (上限 ¥{per_person}/人)",
                  [m["source_file"]])
        else:
            r.add("fail", "MEA-B02", "商务餐人均超标",
                  f"{m['source_file']}: ¥{amount:.0f} / {guest_count}人 = "
                  f"¥{avg:.0f}/人 (上限 ¥{per_person}/人，超出 ¥{avg - per_person:.0f})",
                  [m["source_file"]], "HIGH")


def check_09_per_diem_calculation(ctx: TripContext, r: AuditResult):
    """MEA-001: 伙食补助天数计算（出发日/返回日半天规则）"""
    if not ctx.trip_start or not ctx.trip_end:
        return

    meal_rules = ctx.rules.get("meals", {})
    if meal_rules.get("mode") != "per_diem":
        return

    per_diem_cfg = meal_rules.get("per_diem", {})
    daily_amounts = per_diem_cfg.get("daily_amount", {})
    half_ratio = per_diem_cfg.get("half_day_ratio", 0.5)

    # 取目的地城市等级
    dest_city = next(iter(ctx.destinations), "")
    c_tier = get_city_tier(dest_city, ctx.city_tiers)

    # per_diem daily_amount 可能是:
    #   1) 城市等级 map: {tier_1: 120, tier_2: 100, tier_3: 80}
    #   2) rank×city 矩阵: {senior: {tier_1:...}, ...}
    #   3) 单一数值: 100
    if isinstance(daily_amounts, (int, float)):
        daily_amount = daily_amounts
    elif any(k.startswith("tier_") for k in daily_amounts):
        # 城市等级 map（无职级维度）
        daily_amount = daily_amounts.get(c_tier, daily_amounts.get("tier_3", 0))
    else:
        # rank×city 矩阵
        daily_amount = get_limit(daily_amounts, ctx.rank_tier, c_tier)

    if not daily_amount or ctx.trip_days <= 0:
        return

    # 计算应发补助: 首日半天 + 中间全天 + 末日半天
    if ctx.trip_days == 1:
        expected = daily_amount * 1  # 当天往返算1天
    else:
        full_days = ctx.trip_days - 2
        expected = daily_amount * (full_days + 2 * half_ratio)

    # 找实际申报的伙食补助
    per_diem_claims = [e for e in ctx.fee_items
                       if e.get("subcategory") == "per_diem"]
    claimed = sum(e.get("amount", 0) for e in per_diem_claims)

    if not per_diem_claims:
        return  # 没有申报伙食补助，不检查

    if abs(claimed - expected) < 1:
        r.add("pass", "MEA-001", "伙食补助金额正确",
              f"申报 ¥{claimed:.0f}，应发 ¥{expected:.0f} "
              f"({ctx.trip_days}天，¥{daily_amount}/日，首末日×{half_ratio})",
              [e["source_file"] for e in per_diem_claims])
    elif claimed < expected:
        r.add("pass", "MEA-001", "伙食补助低于应发额（可能已扣除接待餐次）",
              f"申报 ¥{claimed:.0f} < 应发 ¥{expected:.0f}",
              [e["source_file"] for e in per_diem_claims])
    else:
        r.add("fail", "MEA-001", "伙食补助超出应发额",
              f"申报 ¥{claimed:.0f} > 应发 ¥{expected:.0f} "
              f"({ctx.trip_days}天，¥{daily_amount}/日，首末日×{half_ratio})，"
              f"多 ¥{claimed - expected:.0f}",
              [e["source_file"] for e in per_diem_claims], "MEDIUM")


# =============================================================================
# ▌ 维度 3: 职级合规 (3项)
# =============================================================================

def check_10_flight_class(ctx: TripContext, r: AuditResult):
    """TRA-F01: 机票舱位 vs 职级限制"""
    flight_cfg = ctx.rules.get("transportation", {}).get("flight", {})
    class_limits = flight_cfg.get("class_limit", {})
    hierarchy = flight_cfg.get("class_hierarchy",
                               ["economy", "premium_economy", "business", "first"])

    flights = [e for e in ctx.fee_items
               if e.get("subcategory") == "flight" or e.get("doc_type") == "ticket"]
    rank = ctx.rank_tier
    max_class = class_limits.get(rank, "economy")
    max_rank = class_rank(max_class, hierarchy)

    for f in flights:
        actual = f.get("flight_class")
        if not actual:
            r.add("unknown", "TRA-F01", "机票舱位信息缺失",
                  f"{f['source_file']}: 无法判断舱位是否合规",
                  [f["source_file"]], "MEDIUM")
            continue

        actual_rank = class_rank(actual, hierarchy)
        if actual_rank < 0:
            r.add("unknown", "TRA-F01", f"未识别的舱位类型: {actual}",
                  f"{f['source_file']}", [f["source_file"]], "MEDIUM")
        elif actual_rank <= max_rank:
            r.add("pass", "TRA-F01", "机票舱位合规",
                  f"{f['source_file']}: {actual} (职级 {rank} 允许 ≤{max_class})",
                  [f["source_file"]])
        else:
            r.add("fail", "TRA-F01", "机票舱位超出职级限制",
                  f"{f['source_file']}: 实际 {actual}，职级 {rank} 最高允许 {max_class}",
                  [f["source_file"]], "HIGH")


def check_11_train_class(ctx: TripContext, r: AuditResult):
    """TRA-T01: 火车座次 vs 职级限制"""
    train_cfg = ctx.rules.get("transportation", {}).get("train", {})
    class_limits = train_cfg.get("class_limit", {})
    hierarchy = train_cfg.get("class_hierarchy", ["second", "first", "business"])

    trains = [e for e in ctx.fee_items if e.get("subcategory") == "train"]
    rank = ctx.rank_tier
    max_class = class_limits.get(rank, "second")
    max_rank_val = class_rank(max_class, hierarchy)

    for t in trains:
        actual = t.get("train_class")
        if not actual:
            r.add("unknown", "TRA-T01", "火车座次信息缺失",
                  f"{t['source_file']}: 无法判断座次是否合规",
                  [t["source_file"]], "MEDIUM")
            continue

        actual_rank = class_rank(actual, hierarchy)
        if actual_rank < 0:
            r.add("unknown", "TRA-T01", f"未识别的座次类型: {actual}",
                  f"{t['source_file']}", [t["source_file"]], "MEDIUM")
        elif actual_rank <= max_rank_val:
            r.add("pass", "TRA-T01", "火车座次合规",
                  f"{t['source_file']}: {actual} (职级 {rank} 允许 ≤{max_class})",
                  [t["source_file"]])
        else:
            r.add("fail", "TRA-T01", "火车座次超出职级限制",
                  f"{t['source_file']}: 实际 {actual}，职级 {rank} 最高允许 {max_class}",
                  [t["source_file"]], "HIGH")


def check_12_approval_threshold(ctx: TripContext, r: AuditResult):
    """GEN-006: 总额审批阈值"""
    thresholds = ctx.rules.get("general", {}).get("approval_thresholds", [])
    if not thresholds or not ctx.total_amount:
        return

    # 从高到低匹配
    sorted_t = sorted(thresholds, key=lambda x: x["amount"], reverse=True)
    for t in sorted_t:
        if ctx.total_amount >= t["amount"]:
            r.add("warning", "GEN-006", "费用达到审批阈值",
                  f"报销总额 ¥{ctx.total_amount:.2f} ≥ ¥{t['amount']}，"
                  f"需 {t['approver']} 审批",
                  severity="MEDIUM")
            return

    r.add("pass", "GEN-006", "费用未达审批阈值",
          f"报销总额 ¥{ctx.total_amount:.2f}，无需额外审批")


# =============================================================================
# ▌ 维度 4: 票据合规 (4项)
# =============================================================================

def check_13_invoice_completeness(ctx: TripContext, r: AuditResult):
    """MIS-002: 票据完整性"""
    comm_no_invoice = ctx.rules.get("communication", {}).get("requires_invoice", True) is False
    no_invoice_subcats = set()
    if comm_no_invoice:
        no_invoice_subcats.add("phone")

    # 伙食补助通常不需要发票
    if ctx.rules.get("meals", {}).get("mode") == "per_diem":
        no_invoice_subcats.add("per_diem")

    for exp in ctx.fee_items:
        if exp.get("has_invoice") is False:
            subcat = exp.get("subcategory", "")
            if subcat in no_invoice_subcats:
                continue
            # 市内公交也可能没有发票
            if subcat == "local_transit":
                r.add("warning", "MIS-002", "市内交通缺少票据",
                      f"{exp['source_file']}: ¥{exp.get('amount', 0):.2f}",
                      [exp["source_file"]], "LOW")
                continue

            r.add("fail", "MIS-002", "缺少发票",
                  f"{exp['source_file']}: {exp.get('description', '')} "
                  f"¥{exp.get('amount', 0):.2f} 无正规发票",
                  [exp["source_file"]], "HIGH")


def check_14_invoice_company_name(ctx: TripContext, r: AuditResult):
    """GEN-004: 发票抬头检查"""
    general = ctx.rules.get("general", {})
    company = general.get("company_name", "")
    aliases = set(general.get("company_name_aliases", []))
    valid_names = {company} | aliases

    if not company or company.startswith("占位符"):
        # 占位符公司名，跳过检查但提示
        r.add("unknown", "GEN-004", "未配置公司名称",
              "规则文件中 company_name 为占位符，无法校验发票抬头",
              severity="LOW")
        return

    for exp in ctx.fee_items:
        inv_name = exp.get("invoice_company_name", "")
        if not inv_name:
            continue  # 没提取到抬头的不检查
        if inv_name in valid_names:
            r.add("pass", "GEN-004", "发票抬头正确",
                  f"{exp['source_file']}: {inv_name}",
                  [exp["source_file"]])
        else:
            r.add("fail", "GEN-004", "发票抬头不一致",
                  f"{exp['source_file']}: 抬头为「{inv_name}」，"
                  f"应为「{company}」",
                  [exp["source_file"]], "HIGH")


def check_15_invoice_number_dedup(ctx: TripContext, r: AuditResult):
    """GEN-007: 电子发票号码去重"""
    seen = {}  # invoice_number → source_file
    for exp in ctx.fee_items:
        inv_num = exp.get("invoice_number", "")
        if not inv_num:
            continue
        if inv_num in seen:
            r.add("fail", "GEN-007", "发票号码重复",
                  f"发票号 {inv_num} 出现在 [{seen[inv_num]}] 和 "
                  f"[{exp['source_file']}] 中",
                  [seen[inv_num], exp["source_file"]], "HIGH")
        else:
            seen[inv_num] = exp["source_file"]


def check_16_business_meal_info(ctx: TripContext, r: AuditResult):
    """MEA-B01: 商务餐事由/陪餐人完整性"""
    meals = [e for e in ctx.fee_items if e.get("subcategory") == "business_meal"]
    for m in meals:
        issues = []
        if not m.get("meal_occasion"):
            issues.append("缺少用餐事由")
        if not m.get("meal_guests") and not m.get("guest_count"):
            issues.append("缺少陪餐人员/人数")

        if issues:
            r.add("warning", "MEA-B01", "商务餐信息不完整",
                  f"{m['source_file']}: {', '.join(issues)}",
                  [m["source_file"]], "MEDIUM")
        else:
            r.add("pass", "MEA-B01", "商务餐信息完整",
                  f"{m['source_file']}: 事由={m.get('meal_occasion','')}, "
                  f"人数={m.get('guest_count','')}",
                  [m["source_file"]])


# =============================================================================
# ▌ 维度 5: 逻辑一致性 (4项)
# =============================================================================

def check_17_location_consistency(ctx: TripContext, r: AuditResult):
    """ACC-003: 费用地点 vs 出差目的地"""
    if not ctx.destinations:
        return

    # 出发地也算合理地点
    ok_cities = ctx.destinations | ctx.departure_cities

    for exp in ctx.fee_items:
        city = (exp.get("location") or {}).get("city", "")
        if not city:
            continue
        if city in ok_cities:
            continue
        # 交通类的出发/到达城市单独判断
        if exp.get("departure_city") or exp.get("arrival_city"):
            continue
        r.add("warning", "ACC-003", "费用发生地与出差目的地不一致",
              f"{exp['source_file']}: 发生在 {city}，"
              f"出差目的地 {', '.join(ctx.destinations)}",
              [exp["source_file"]], "MEDIUM")


def check_18_transport_route_logic(ctx: TripContext, r: AuditResult):
    """GEN-010: 交通路线逻辑性"""
    transports = [e for e in ctx.fee_items
                  if e.get("category") == "transportation"
                  and (e.get("departure_city") and e.get("arrival_city"))]
    if len(transports) < 2:
        return

    # 按日期排序
    transports.sort(key=lambda x: str(x.get("date", "")))

    # 检查链式连接: 上一段的到达城市应为下一段的出发城市
    for i in range(len(transports) - 1):
        curr = transports[i]
        nxt = transports[i + 1]
        if curr.get("arrival_city") and nxt.get("departure_city"):
            if curr["arrival_city"] != nxt["departure_city"]:
                # 允许同城间隔（比如到达上海后市内活动，后从上海出发）
                # 但如果到达北京、下一段从广州出发，就有问题
                r.add("warning", "GEN-010", "交通路线不连续",
                      f"{curr['source_file']}→{nxt['source_file']}: "
                      f"到达 {curr['arrival_city']} 后下一段从 "
                      f"{nxt['departure_city']} 出发",
                      [curr["source_file"], nxt["source_file"]], "MEDIUM")


def check_19_same_day_same_type(ctx: TripContext, r: AuditResult):
    """GEN-008: 同日多笔同类费用"""
    # 按 (日期, 子类别) 分组
    groups = defaultdict(list)
    for exp in ctx.fee_items:
        d = exp.get("date", "")
        subcat = exp.get("subcategory", exp.get("category", "other"))
        if d and subcat:
            groups[(d, subcat)].append(exp)

    # 某些类别同日多笔是正常的（出租车多次打车）
    normal_multi = {"taxi", "rideshare", "local_transit", "phone", "per_diem",
                    "other", "business_meal"}

    for (date, subcat), items in groups.items():
        if len(items) <= 1:
            continue
        if subcat in normal_multi:
            continue  # 出租车/市内交通同日多笔正常
        files = [e["source_file"] for e in items]
        total = sum(e.get("amount", 0) for e in items)
        r.add("warning", "GEN-008", f"同日多笔{subcat}费用",
              f"{date}: {len(items)} 笔 {subcat}，"
              f"合计 ¥{total:.2f}，文件: {', '.join(files)}",
              files, "HIGH")


def check_20_duplicate_detection(ctx: TripContext, r: AuditResult):
    """GEN-003: 疑似重复报销"""
    thr = ctx.thresholds
    amt_tol = thr.get("duplicate_amount_threshold", 0.01)
    date_range = thr.get("duplicate_date_range_days", 3)

    by_cat = defaultdict(list)
    for e in ctx.fee_items:
        by_cat[e.get("category", "other")].append(e)

    checked_pairs = set()
    for cat, items in by_cat.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                pair_key = (a.get("source_file", ""), b.get("source_file", ""))
                if pair_key in checked_pairs:
                    continue

                amt_a, amt_b = a.get("amount", 0), b.get("amount", 0)
                if amt_a == 0 or amt_b == 0:
                    continue
                if abs(amt_a - amt_b) / max(amt_a, amt_b) > amt_tol:
                    continue

                da, db = parse_date(a.get("date")), parse_date(b.get("date"))
                if da and db and abs((da - db).days) <= date_range:
                    checked_pairs.add(pair_key)
                    r.add("warning", "GEN-003", "疑似重复费用",
                          f"[{a['source_file']}] ¥{amt_a:.2f} ({a.get('date')}) vs "
                          f"[{b['source_file']}] ¥{amt_b:.2f} ({b.get('date')}) — "
                          f"同类({cat})，金额接近，日期相差{abs((da-db).days)}天",
                          [a["source_file"], b["source_file"]], "HIGH")


# =============================================================================
# 主引擎
# =============================================================================

ALL_CHECKS = [
    # 维度1: 时间
    check_01_date_in_range,
    check_02_hotel_nights_vs_trip,
    check_03_reimbursement_deadline,
    check_04_weekend_holiday,
    # 维度2: 金额
    check_05_amount_consistency,
    check_06_accommodation_limit,
    check_07_taxi_daily_limit,
    check_08_business_meal_limit,
    check_09_per_diem_calculation,
    # 维度3: 职级
    check_10_flight_class,
    check_11_train_class,
    check_12_approval_threshold,
    # 维度4: 票据
    check_13_invoice_completeness,
    check_14_invoice_company_name,
    check_15_invoice_number_dedup,
    check_16_business_meal_info,
    # 维度5: 逻辑
    check_17_location_consistency,
    check_18_transport_route_logic,
    check_19_same_day_same_type,
    check_20_duplicate_detection,
]


def run_audit(expenses: list[dict], rules: dict) -> dict:
    ctx = TripContext(expenses, rules)
    result = AuditResult()

    for check_fn in ALL_CHECKS:
        try:
            check_fn(ctx, result)
        except Exception as exc:
            result.add("unknown", "SYS-ERR",
                       f"检查 {check_fn.__name__} 执行异常",
                       str(exc), severity="LOW")

    # 附加上下文摘要
    output = result.to_dict()
    output["context"] = {
        "trip_start": str(ctx.trip_start.date()) if ctx.trip_start else None,
        "trip_end": str(ctx.trip_end.date()) if ctx.trip_end else None,
        "trip_days": ctx.trip_days,
        "rank_tier": ctx.rank_tier,
        "destinations": list(ctx.destinations),
        "total_amount": ctx.total_amount,
        "submission_date": str(ctx.submission_date.date()) if ctx.submission_date else None,
        "expense_count": len(ctx.fee_items),
        "checks_executed": len(ALL_CHECKS),
    }
    return output


def main():
    parser = argparse.ArgumentParser(description="出差报销审计引擎 v2.0")
    parser.add_argument("--expenses", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--output", default="/home/claude/audit_results.json")
    args = parser.parse_args()

    expenses = load_json(args.expenses)
    rules = load_yaml(args.rules)
    results = run_audit(expenses, rules)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    s = results["summary"]
    c = results["context"]
    print(f"\n{'='*60}")
    print("审计引擎 v2.0 — 执行完成")
    print(f"{'='*60}")
    print(f"  出差人职级: {c['rank_tier']}")
    print(f"  出差期间:   {c['trip_start']} ~ {c['trip_end']} ({c['trip_days']}天)")
    print(f"  报销总额:   ¥{c['total_amount']:.2f}")
    print(f"  费用笔数:   {c['expense_count']}")
    print(f"  检查维度:   {c['checks_executed']} 类")
    print(f"{'─'*60}")
    print(f"  ✅ 通过:    {s['pass']}")
    print(f"  ⚠️  警告:    {s['warning']}")
    print(f"  ❌ 违规:    {s['fail']}")
    print(f"  ❓ 待确认:  {s['unknown']}")
    print(f"{'='*60}")
    print(f"结果: {args.output}")


if __name__ == "__main__":
    main()

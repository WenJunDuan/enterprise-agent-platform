"""Domain models derived from handbook policies and future audit workflows."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DocumentType = Literal[
    "travel_request",
    "leave_request",
    "expense_claim",
    "loan_request",
    "entertainment_request",
    "other",
]
ApprovalResult = Literal["pending", "approved", "rejected", "cancelled"]
LeaveType = Literal[
    "annual_leave",
    "sick_leave",
    "personal_leave",
    "marriage_leave",
    "bereavement_leave",
    "maternity_leave",
    "paternity_or_nursing_leave",
    "other",
]
ClaimType = Literal["travel", "entertainment", "transport", "team_building", "general", "other"]
BudgetStatus = Literal["unknown", "within_budget", "over_budget", "missing_budget"]
RepaymentStatus = Literal["pending", "partially_repaid", "repaid", "overdue"]
RuleDomain = Literal["expense", "hr", "legal", "cross_domain"]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmployeeContext(DomainModel):
    employee_id: str
    employee_name: str | None = None
    department: str | None = None
    position: str | None = None
    job_level: str | None = None
    base_city: str | None = None
    company_entity: str | None = None
    employment_type: str | None = None
    attendance_type: str | None = None


class ApprovalRecord(DomainModel):
    approval_id: str
    document_type: DocumentType
    document_id: str
    approver_role: str
    approver_name: str | None = None
    approval_node: str
    approval_result: ApprovalResult = "pending"
    approval_time: datetime | None = None
    approval_comment: str | None = None


class TravelRequest(DomainModel):
    travel_id: str
    applicant_id: str
    department: str | None = None
    project: str | None = None
    customer: str | None = None
    purpose: str
    confidential_flag: bool = False
    origin_city: str | None = None
    destination_city: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    estimated_days: float | None = None
    estimated_amount: float | None = None
    transport_plan: list[str] = Field(default_factory=list)
    lodging_plan: list[str] = Field(default_factory=list)
    allowance_days: float | None = None
    status: str = "draft"
    approval_chain: list[ApprovalRecord] = Field(default_factory=list)
    change_required: bool = False


class LeaveRequest(DomainModel):
    leave_id: str
    applicant_id: str
    leave_type: LeaveType
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    leave_days: float | None = None
    reason: str | None = None
    medical_docs: list[str] = Field(default_factory=list)
    urgent_flag: bool = False
    salary_impact: str | None = None
    hr_required: bool = False
    status: str = "draft"
    approval_chain: list[ApprovalRecord] = Field(default_factory=list)


class ExpenseLineItem(DomainModel):
    category: str
    amount: float
    description: str | None = None
    occurred_on: date | None = None
    related_project: str | None = None
    over_standard_flag: bool = False
    notes: str | None = None


class InvoiceEvidence(DomainModel):
    invoice_id: str
    invoice_type: str
    invoice_date: date | None = None
    invoice_amount: float
    invoice_entity: str | None = None
    invoice_title: str | None = None
    original_available: bool = True
    is_e_invoice: bool = False
    is_duplicate_risk: bool = False
    receipt_type: str | None = None
    trip_statement: str | None = None
    attachment_type: str | None = None


class ExpenseClaim(DomainModel):
    claim_id: str
    claim_type: ClaimType
    applicant_id: str
    benefit_department: str | None = None
    benefit_project: str | None = None
    budget_owner: str | None = None
    related_travel_id: str | None = None
    related_entertainment_id: str | None = None
    related_loan_id: str | None = None
    expense_date: date | None = None
    submit_date: date | None = None
    amount: float | None = None
    line_items: list[ExpenseLineItem] = Field(default_factory=list)
    invoice_list: list[InvoiceEvidence] = Field(default_factory=list)
    paper_docs_submitted: bool = False
    budget_status: BudgetStatus = "unknown"
    over_standard_flag: bool = False
    over_budget_flag: bool = False
    status: str = "draft"


class LoanRequest(DomainModel):
    loan_id: str
    department: str
    applicant_role: str
    amount: float
    purpose: str
    promised_repayment_date: date | None = None
    related_business_id: str | None = None
    repayment_status: RepaymentStatus = "pending"
    outstanding_amount: float | None = None
    status: str = "draft"


class PolicyRule(DomainModel):
    rule_id: str
    domain: RuleDomain
    category: str
    sub_category: str | None = None
    rule_name: str
    trigger_condition: str
    required_precondition: str | None = None
    threshold_operator: str | None = None
    threshold_value: str | float | int | bool | None = None
    required_attachments: list[str] = Field(default_factory=list)
    approval_requirement: str | None = None
    calculation_formula: str | None = None
    exception_condition: str | None = None
    violation_action: str | None = None
    source_chapter: str | None = None
    source_page_range: str | None = None


__all__ = [
    "ApprovalRecord",
    "EmployeeContext",
    "ExpenseClaim",
    "ExpenseLineItem",
    "InvoiceEvidence",
    "LeaveRequest",
    "LoanRequest",
    "PolicyRule",
    "TravelRequest",
]

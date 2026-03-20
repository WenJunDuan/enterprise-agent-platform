from server.models import (
    ApprovalRecord,
    EmployeeContext,
    ExpenseClaim,
    ExpenseLineItem,
    InvoiceEvidence,
    LeaveRequest,
    LoanRequest,
    PolicyRule,
    TravelRequest,
)


def test_server_models_cover_handbook_business_objects() -> None:
    employee = EmployeeContext(
        employee_id="EMP-001",
        employee_name="Alice",
        department="Sales",
        position="Account Manager",
        job_level="L2",
        base_city="Nanjing",
    )

    approval = ApprovalRecord(
        approval_id="APR-001",
        document_type="travel_request",
        document_id="TR-001",
        approver_role="manager",
        approval_node="department_manager",
        approval_result="approved",
    )

    travel_request = TravelRequest(
        travel_id="TR-001",
        applicant_id=employee.employee_id,
        purpose="customer visit",
        origin_city="Nanjing",
        destination_city="Shanghai",
        approval_chain=[approval],
    )

    leave_request = LeaveRequest(
        leave_id="LV-001",
        applicant_id=employee.employee_id,
        leave_type="sick_leave",
        reason="fever",
    )

    expense_claim = ExpenseClaim(
        claim_id="CL-001",
        claim_type="travel",
        applicant_id=employee.employee_id,
        line_items=[
            ExpenseLineItem(
                category="lodging",
                amount=480.0,
                description="hotel",
            )
        ],
        invoice_list=[
            InvoiceEvidence(
                invoice_id="INV-001",
                invoice_amount=480.0,
                invoice_type="electronic",
            )
        ],
    )

    loan_request = LoanRequest(
        loan_id="LN-001",
        department="Sales",
        applicant_role="department_head",
        amount=5000.0,
        purpose="client event advance",
    )

    policy_rule = PolicyRule(
        rule_id="expense.travel.001",
        domain="expense",
        category="travel",
        rule_name="travel pre-approval required",
        trigger_condition="claim_type == 'travel'",
    )

    assert travel_request.approval_chain[0].approval_result == "approved"
    assert leave_request.leave_type == "sick_leave"
    assert expense_claim.invoice_list[0].invoice_amount == 480.0
    assert loan_request.amount == 5000.0
    assert policy_rule.domain == "expense"


def test_policy_rule_and_expense_claim_schemas_expose_core_fields() -> None:
    claim_schema = ExpenseClaim.model_json_schema()
    rule_schema = PolicyRule.model_json_schema()

    assert "claim_id" in claim_schema["properties"]
    assert "claim_type" in claim_schema["properties"]
    assert "line_items" in claim_schema["properties"]
    assert "invoice_list" in claim_schema["properties"]

    assert "rule_id" in rule_schema["properties"]
    assert "domain" in rule_schema["properties"]
    assert "category" in rule_schema["properties"]
    assert "required_attachments" in rule_schema["properties"]

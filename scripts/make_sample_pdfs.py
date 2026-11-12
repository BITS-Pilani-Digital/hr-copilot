"""Generate the fictional HR policy PDFs used in the workshop.

Run:  python scripts/make_sample_pdfs.py    (needs: pip install reportlab)
Replace data/policies/*.pdf with your own documents to make the copilot answer from your data.
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parent.parent / "data" / "policies"
COMPANY = "Nimbus Labs"

POLICIES = {
    "leave_policy.pdf": ("Leave Policy", "HR-POL-001, version 3.2, effective 1 January 2026", [
        [("1. Purpose and scope",
          f"This policy explains the types of leave available to permanent employees of {COMPANY} in India, "
          "how leave is accrued, and how to apply for it. Contractors and interns follow the terms in their contracts."),
         ("2. Annual leave",
          "Permanent employees are entitled to 24 days of annual (privilege) leave per calendar year, accrued at "
          "2 days per completed month of service. Employees in their first year receive leave pro rata from their "
          "joining date. Annual leave is counted in working days; weekends and public holidays inside a leave "
          "period are not deducted."),
         ("3. Carry forward and encashment",
          "Up to 10 days of unused annual leave can be carried forward to the next calendar year. Any balance above "
          "10 days lapses on 31 December. Carried-forward leave must be used by 31 March of the following year. "
          "Leave encashment is only available on resignation or retirement, for a maximum of 30 days, calculated "
          "on basic salary.")],
        [("4. Sick leave",
          "Employees receive 12 days of paid sick leave per calendar year. Sick leave does not carry forward. "
          "A medical certificate is required for sick leave of more than 2 consecutive working days. Sick leave "
          "may be applied retrospectively within 7 days of returning to work."),
         ("5. Casual leave",
          "Employees receive 6 days of casual leave per year for personal matters. Casual leave cannot be combined "
          "with annual leave and may be taken for a maximum of 3 consecutive days."),
         ("6. Applying for leave",
          "Leave is applied for through the HR portal or the HR Copilot, and is approved by the reporting manager. "
          "Annual leave of more than 3 working days must be applied for at least 2 weeks in advance. Requests are "
          "considered approved only after the manager approves them in the system. Managers should respond to "
          "leave requests within 3 working days.")],
        [("7. Parental leave",
          "Birthing parents are entitled to 26 weeks of paid maternity leave, in line with the Maternity Benefit "
          "Act. Non-birthing parents, including adoptive parents, are entitled to 4 weeks of paid paternity or "
          "partner leave, to be taken within 6 months of the birth or adoption."),
         ("8. Other leave",
          "Bereavement leave: up to 5 working days for the loss of an immediate family member. "
          "Marriage leave: 5 working days, once during employment. Leave without pay may be granted for up to "
          "3 months with HR business partner and department head approval."),
         ("9. Contact",
          "Questions about this policy can be sent to hr-help@nimbuslabs.example or raised through the HR Copilot.")],
    ]),
    "remote_work_policy.pdf": ("Hybrid and Remote Work Policy", "HR-POL-004, version 2.0, effective 1 April 2026", [
        [("1. Hybrid working model",
          f"{COMPANY} follows a hybrid model. Employees are expected to work from their assigned office at least "
          "3 days per week, with Tuesday and Wednesday as common team days. Teams may agree on the third day."),
         ("2. Fully remote work",
          "Fully remote arrangements require approval from the department head and HR, and are reviewed every 6 "
          "months. Employees may work remotely from another city in India for up to 4 weeks per year with manager "
          "approval. Working from outside India requires prior approval from HR and Legal because of tax and "
          "immigration rules."),
         ("3. Home office allowance",
          "Employees receive a one-time home office allowance of INR 15,000 for furniture and accessories, and an "
          "internet reimbursement of up to INR 1,500 per month, claimed through the expense portal with receipts.")],
        [("4. Equipment and security",
          "Company laptops must be used for all work. Do not use public Wi-Fi without the company VPN. "
          "Confidential documents must not be printed at home. Lost or stolen devices must be reported to IT "
          "Security within 24 hours."),
         ("5. Working hours",
          "Core collaboration hours are 11:00 to 16:00 IST. Outside these hours employees can manage their time "
          "flexibly, provided they meet their team commitments.")],
    ]),
    "travel_expense_policy.pdf": ("Travel and Expense Policy", "FIN-POL-007, version 5.1, effective 1 January 2026", [
        [("1. Approvals",
          "All business travel must be approved by the reporting manager before booking. International travel "
          "also requires department head approval. Book travel through the corporate travel desk."),
         ("2. Flights and trains",
          "Economy class is used for flights. Business class is allowed for flights longer than 8 hours. "
          "AC 2-tier is allowed for train travel."),
         ("3. Hotels and daily allowance",
          "Hotel limits per night: INR 7,000 in metro cities (Mumbai, Delhi NCR, Bengaluru, Chennai, Hyderabad, "
          "Kolkata, Pune) and INR 5,000 in other cities. The daily allowance for meals and local travel is "
          "INR 2,000 in India. International per diems follow the country table published by Finance.")],
        [("4. Submitting expenses",
          "Expense claims must be submitted within 30 days of the travel end date with itemised receipts. "
          "Receipts are required for any expense above INR 500. Claims are reimbursed in the next payroll cycle "
          "after manager approval."),
         ("5. Non-reimbursable expenses",
          "Alcohol, personal entertainment, traffic fines, minibar charges and upgrades not covered by this "
          "policy are not reimbursable.")],
    ]),
}


def build(filename: str, title: str, subtitle: str, pages: list) -> None:
    styles = getSampleStyleSheet()
    story = []
    for i, sections in enumerate(pages):
        if i == 0:
            story += [Paragraph(f"{COMPANY} - {title}", styles["Title"]),
                      Paragraph(subtitle, styles["Italic"]), Spacer(1, 12)]
        for heading, body in sections:
            story += [Paragraph(heading, styles["Heading2"]), Paragraph(body, styles["BodyText"]), Spacer(1, 8)]
        if i < len(pages) - 1:
            story.append(PageBreak())
    SimpleDocTemplate(str(OUT / filename), pagesize=A4, title=title, author=f"{COMPANY} HR").build(story)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (title, subtitle, pages) in POLICIES.items():
        build(name, title, subtitle, pages)
        print("wrote", OUT / name)

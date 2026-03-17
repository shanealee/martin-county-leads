"""
Email sender for weekly restaurant lead reports.
Uses SendGrid free tier (100 emails/day).
"""

import os
import json
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import base64


def format_leads_html(leads):
    """Format leads into a nice HTML email body."""
    run_date = datetime.now().strftime("%B %d, %Y")

    # Group by source
    by_source = {}
    for lead in leads:
        src = lead.get("source", "Unknown")
        by_source.setdefault(src, []).append(lead)

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; color: #333;">
        <div style="background: #1F4E79; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; font-size: 22px;">New Restaurant Leads - Martin County, FL</h1>
            <p style="margin: 5px 0 0 0; opacity: 0.9;">Weekly Report - {run_date}</p>
        </div>

        <div style="padding: 20px; background: #f9f9f9;">
            <p style="font-size: 16px; color: #1F4E79; font-weight: bold;">
                {len(leads)} lead(s) found this week
            </p>
    """

    if not leads:
        html += """
            <div style="background: white; padding: 20px; border-radius: 8px; border: 1px solid #ddd;">
                <p>No new leads found this week. The scraper checked all sources —
                nothing new in Martin County. Will check again next week.</p>
            </div>
        """
    else:
        # Priority: DBPR/Sunbiz first (most actionable), then news
        source_order = [
            "FL DBPR New Food License",
            "FL DBPR License Portal",
            "Sunbiz LLC Filing",
            "Google News",
            "HometownNewsTC",
            "BusinessDebut"
        ]

        for source in source_order:
            if source not in by_source:
                continue
            source_leads = by_source[source]

            source_colors = {
                "FL DBPR New Food License": "#CC0000",
                "FL DBPR License Portal": "#CC0000",
                "Sunbiz LLC Filing": "#996600",
                "Google News": "#006600",
                "HometownNewsTC": "#006600",
                "BusinessDebut": "#006600",
            }
            color = source_colors.get(source, "#333")

            html += f"""
            <div style="margin-top: 20px;">
                <h2 style="font-size: 16px; color: {color}; border-bottom: 2px solid {color}; padding-bottom: 5px;">
                    {source} ({len(source_leads)} found)
                </h2>
            """

            for lead in source_leads:
                name = lead.get("name") or lead.get("dba") or "Unknown"
                address = lead.get("address", "")
                city = lead.get("city", "")
                status = lead.get("status", "")
                url = lead.get("url") or lead.get("detail_url", "")

                html += f"""
                <div style="background: white; padding: 15px; border-radius: 6px; border: 1px solid #ddd; margin-bottom: 10px;">
                    <strong style="font-size: 14px;">{name}</strong><br>
                """
                if address or city:
                    html += f'<span style="color: #666;">{address} {city}</span><br>'
                if status:
                    html += f'<span style="background: #e8f4e8; padding: 2px 8px; border-radius: 3px; font-size: 12px;">{status}</span>'
                if url:
                    html += f' <a href="{url}" style="font-size: 12px;">View source</a>'
                html += "</div>"

            html += "</div>"

    html += """
        <div style="margin-top: 30px; padding-top: 15px; border-top: 1px solid #ddd; font-size: 12px; color: #999;">
            <p><strong>Sources checked:</strong> FL DBPR licenses, Sunbiz LLC filings,
            Google News, HometownNewsTC, BusinessDebut.com</p>
            <p><strong>Tip:</strong> DBPR and Sunbiz leads are the hottest — these are businesses
            filing official paperwork, often before they even open.</p>
        </div>
        </div>
    </body>
    </html>
    """
    return html


def send_email(leads, recipient_email=None):
    """Send the weekly lead report via SendGrid."""
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key:
        print("ERROR: SENDGRID_API_KEY environment variable not set")
        return False

    sender = os.environ.get("SENDER_EMAIL", "leads@yourdomain.com")
    recipient = recipient_email or os.environ.get("RECIPIENT_EMAIL", "shanealee@icloud.com")

    run_date = datetime.now().strftime("%m/%d/%Y")
    subject = f"Martin County Restaurant Leads - {run_date} ({len(leads)} found)"

    html_content = format_leads_html(leads)

    message = Mail(
        from_email=sender,
        to_emails=recipient,
        subject=subject,
        html_content=html_content
    )

    # Attach raw JSON data
    if leads:
        json_data = json.dumps(leads, indent=2, default=str)
        encoded = base64.b64encode(json_data.encode()).decode()
        attachment = Attachment(
            FileContent(encoded),
            FileName(f"leads_{datetime.now().strftime('%Y%m%d')}.json"),
            FileType("application/json"),
            Disposition("attachment")
        )
        message.attachment = attachment

    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        print(f"Email sent! Status: {response.status_code}")
        print(f"  To: {recipient}")
        print(f"  Subject: {subject}")
        return True
    except Exception as e:
        print(f"Email failed: {e}")
        return False


if __name__ == "__main__":
    # Test with sample data
    sample = [{"source": "Test", "name": "Test Restaurant", "status": "Test Lead", "date_found": "2026-03-16"}]
    send_email(sample)

import streamlit as st
import pandas as pd
import io
import smtplib
import psycopg2
from email.message import EmailMessage
import plotly.express as px
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ───────────────────────────────────────────────────────────
# 🔧 Streamlit Config
st.set_page_config(page_title="Lead Dashboard", page_icon="📊", layout="wide")

# 🔒 Session State Init
if "notified_leads" not in st.session_state:
    st.session_state["notified_leads"] = set()

# Database connection
def get_connection():
    return psycopg2.connect(
        "postgresql://postgres:Apple1317..!!@db.cypkfsuwwyifpaiqvvjg.supabase.co:5432/postgres?sslmode=require"
    )

# 🌙 Dark Theme + Apple-style Visuals
st.markdown("""
    <style>
    .appview-container .main {
        padding: 3rem 4rem;
        background-color: #121212;
        color: #EDEDED;
    }
    .sidebar .sidebar-content {
        background-color: #1E1E1E;
    }
    .stApp, .stMarkdown, .stText, [data-testid="metric-container"] * {
        color: #EDEDED !important;
    }
    h1, h2, h3, h4 {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        color: #FFF !important;
        font-weight: 700;
        margin-bottom: 0.75rem;
    }
    [data-testid="metric-container"] {
        background-color: #1E1E1E;
        border-radius: 1rem;
        padding: 1.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.25);
        margin: 1rem 0;
    }
    .stButton>button, .stDownloadButton>button {
        background-color: #007AFF !important;
        color: white !important;
        border-radius: 0.75rem !important;
        padding: 0.6rem 1.2rem !important;
        font-weight: 600 !important;
        border: none !important;
    }
    .stButton>button:hover, .stDownloadButton>button:hover {
        background-color: #005BBB !important;
    }
    .stDataFrame tbody tr {
        background-color: #1E1E1E;
        color: #EDEDED;
    }
    </style>
""", unsafe_allow_html=True)

# 🏡 Header
st.title("🏡 New Coast Collective")
st.subheader("Real-Estate Lead Dashboard")

# 📝 Add New Lead Form
st.markdown("### ➕ Add New Lead")

with st.form("add_lead_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name")
        email = st.text_input("Email")
        zipcode = st.text_input("Zipcode")
    with col2:
        property_type = st.selectbox("Property Type", ["House", "Condo", "Land", "Townhouse", "Commercial"])
        status = st.selectbox("Lead Status", ["New", "Hot", "Cold", "Contacted", "Investor"])
        inquiry_date = st.date_input("Inquiry Date")
    
    submitted = st.form_submit_button("Add Lead")

    if submitted:
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO leads (name, email, zipcode, property_type, status, inquiry_date)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, email, zipcode, property_type, status, inquiry_date))
            conn.commit()
            cur.close()
            conn.close()
            st.success(f"✅ Lead for {name} added successfully!")
            st.experimental_rerun()  # refresh dashboard after adding
        except Exception as e:
            st.error(f"❌ Failed to add lead: {e}")

# 📂 Load Data
def load_leads():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM leads", conn)
    conn.close()
    return df

# Load the leads
df = load_leads()


# 🎛 Sidebar Filters
st.sidebar.header("🔍 Filter Leads")
start_date, end_date = st.sidebar.date_input(
    "Select Inquiry Date Range",
    [df["inquiry_date"].min(), df["inquiry_date"].max()]
)
zipcodes = st.sidebar.multiselect("Filter by Zip Code",
    options=sorted(df["zipcode"].astype(str).unique()),
    default=sorted(df["zipcode"].astype(str).unique()))
property_types = st.sidebar.multiselect("Filter by Property Type",
    options=sorted(df["property_type"].unique()),
    default=sorted(df["property_type"].unique()))
search_query = st.sidebar.text_input("Search by Name or Email").lower()
sort_by = st.sidebar.selectbox("Sort Leads By", ["inquiry_date", "lead_score", "name"])

# 🔍 Apply Filters
df = df[
    (df["inquiry_date"] >= pd.to_datetime(start_date)) &
    (df["inquiry_date"] <= pd.to_datetime(end_date)) &
    (df["zipcode"].astype(str).isin(zipcodes)) &
    (df["property_type"].isin(property_types))
]
if search_query:
    df = df[
        df["name"].str.lower().str.contains(search_query) |
        df["email"].str.lower().str.contains(search_query)
    ]

# 🧠 Lead Scoring
def score_lead(status):
    s = status.lower()
    if "hot" in s: return 100
    if "investor" in s: return 85
    if "contacted" in s: return 70
    if "new" in s: return 50
    if "cold" in s: return 20
    return 0

df["lead_score"] = df["status"].apply(score_lead)
df = df.sort_values(by=sort_by, ascending=False if sort_by != "name" else True)
hot_leads = df[df["status"].str.lower().str.contains("hot")]
new_hot_leads = hot_leads[~hot_leads["email"].isin(st.session_state["notified_leads"])]

# 📊 Status Chart
status_counts = df["status"].str.lower().value_counts().rename_axis("status").reset_index(name="count")
fig = px.bar(status_counts, x="status", y="count", template="simple_white", labels={"status": "Lead Status", "count": "Count"})
fig.update_layout(showlegend=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=30, b=10))
st.plotly_chart(fig, use_container_width=True)

# 📧 Email Alert for Hot Leads
if not new_hot_leads.empty:
    top_lead = new_hot_leads.iloc[0]
    alert = EmailMessage()
    alert["Subject"] = "🚨 New Hot Lead Alert!"
    alert["From"] = st.secrets["email"]["sender"]
    alert["To"] = st.secrets["email"]["receiver"]
    alert.set_content(f"You have {len(new_hot_leads)} new hot lead(s).\n\nTop lead: {top_lead['name']} — {top_lead['email']}")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(alert["From"], st.secrets["email"]["password"])
            smtp.send_message(alert)
        st.success("📧 New hot-lead alert sent!")
        st.session_state["notified_leads"].update(new_hot_leads["email"].tolist())
    except Exception as e:
        st.warning(f"⚠️ Hot-lead email failed: {e}")

# 📈 Metrics
st.markdown("### 📈 Key Metrics")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Leads", len(df))
c2.metric("🔥 Hot Leads", len(hot_leads))
c3.metric("⭐ Avg. Lead Score", round(df["lead_score"].mean(), 1))
c4.metric("🏘 Top Property Type", df["property_type"].mode()[0])
c5.metric("📍 Top Zip Code", df["zipcode"].mode()[0])

# 🧠 Advanced Insights
st.markdown("### 🧠 Advanced Insights")
a1, a2, a3 = st.columns(3)
conv_pot = df["status"].str.lower().str.contains("hot|investor").sum() / len(df) * 100 if len(df) else 0
lag_days = (pd.Timestamp.today() - df["inquiry_date"]).dt.days.mean()
best_zip = df.groupby("zipcode")["lead_score"].mean().idxmax() if not df.empty else "N/A"
a1.metric("🔑 Conversion Potential", f"{conv_pot:.1f}%")
a2.metric("⏳ Avg. Inquiry Lag (days)", round(lag_days, 1))
a3.metric("💸 Best Zip by Score", best_zip)

# 📋 CRM Table
st.markdown("### 📋 CRM Data")
with st.expander("📋 View All CRM Leads"):
    st.dataframe(df)
with st.expander("🔥 View Hot Leads"):
    st.dataframe(hot_leads)

# 💾 Download Buttons
buf = io.BytesIO()
df.to_excel(buf, index=False, engine="xlsxwriter")
buf.seek(0)
st.markdown("#### 💾 Download Filtered Leads")
st.download_button("⬇️ Download Excel", data=buf, file_name="filtered_leads.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
st.download_button("⬇️ Download CSV", data=df.to_csv(index=False).encode("utf-8"), file_name="filtered_leads.csv", mime="text/csv")

# 📧 Email Report to Yourself
if st.button("📧 Email Report to Me"):
    buf.seek(0)
    report = EmailMessage()
    report["Subject"] = "Filtered Leads Report"
    report["From"] = st.secrets["email"]["sender"]
    report["To"] = st.secrets["email"]["receiver"]
    report.set_content("Attached is your filtered lead report.")
    report.add_attachment(buf.getvalue(), maintype="application", subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="filtered_leads.xlsx")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(report["From"], st.secrets["email"]["password"])
            smtp.send_message(report)
        st.success("✅ Email sent successfully!")
    except Exception as e:
        st.error(f"❌ Failed to send email: {e}")

# ☁️ Upload to Google Drive
def upload_to_gdrive(buffer, fname):
    creds = service_account.Credentials.from_service_account_file(".streamlit/gdrive_service_account.json")
    drive = build("drive", "v3", credentials=creds)
    media = MediaIoBaseUpload(buffer, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    meta = {"name": fname}
    created = drive.files().create(body=meta, media_body=media, fields="id").execute()
    return f"https://drive.google.com/file/d/{created['id']}/view"

if st.button("📤 Upload to Google Drive"):
    try:
        buf.seek(0)
        link = upload_to_gdrive(buf, "filtered_leads.xlsx")
        st.success("✅ Uploaded to Google Drive!")
        st.markdown(f"[🔗 View in Drive]({link})", unsafe_allow_html=True)
    except Exception as e:
        st.error(f"❌ Failed to upload to Drive: {e}")

# 🤖 Smart Suggestions
st.markdown("### 🤖 Smart Suggestions")
if conv_pot > 50:
    st.success(f"💡 Strong conversion potential! Focus on {best_zip}.")
elif lag_days > 30:
    st.warning("⏱️ Leads are aging. Follow up sooner.")
else:
    st.info("📊 Monitor lead patterns weekly for optimization.")

import streamlit as st
import pandas as pd
import os
import json
from google import genai
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
from google.oauth2 import service_account
from googleapiclient.discovery import build

st.set_page_config(page_title="Shiksha Yield% Hub", layout="wide")
st.title("🎯 Shiksha.com Automated SEO Yield% Hub")

# 1. Secure API Connections via Streamlit Secrets
try:
    # Load Google Service Account Credentials from background environment
    google_creds = json.loads(st.secrets["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
    scoped_creds = service_account.Credentials.from_service_account_info(
        google_creds, 
        scopes=['https://googleapis.com', 'https://googleapis.com']
    )
    
    # Load Gemini API Key
    gemini_key = st.secrets["GUIDE_GEMINI_KEY"]
    ai_client = genai.Client(api_key=gemini_key)
    st.sidebar.success("🔑 All Cloud APIs Connected Securely!")
except Exception as e:
    st.sidebar.error(f"❌ Connection configuration missing: {str(e)}")
    st.stop()

# 2. Sidebar Input Controls for the SEO Team
st.sidebar.subheader("🎛️ Audit Controls")
gsc_site_url = st.sidebar.text_input("GSC Property URL", "https://shiksha.com")
ga4_property_id = st.sidebar.text_input("GA4 Property ID (Numbers only)", "123456789")
start_date = st.sidebar.date_input("Start Date", pd.to_datetime("today") - pd.Timedelta(days=30))
end_date = st.sidebar.date_input("End Date", pd.to_datetime("today"))

if st.sidebar.button("⚡ Execute Live Audit"):
    with st.spinner("Pulling data from Google Search Console and Analytics APIs..."):
        try:
            # ----------------------------------------------------
            # 🟢 PULL live GSC DATA (0 TOKENS)
            # ----------------------------------------------------
            gsc_service = build('webmasters', 'v3', credentials=scoped_creds)
            gsc_request = {
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'dimensions': ['page'],
                'rowLimit': 100
            }
            gsc_response = gsc_service.searchanalytics().query(siteUrl=gsc_site_url, body=gsc_request).execute()
            
            gsc_records = []
            if 'rows' in gsc_response:
                for row in gsc_response['rows']:
                    gsc_records.append({
                        'URL': row['keys'][0],
                        'Impressions': row['impressions'],
                        'Clicks': row['clicks']
                    })
            gsc_df = pd.DataFrame(gsc_records)

            # ----------------------------------------------------
            # 🟢 PULL live GA4 DATA (0 TOKENS)
            # ----------------------------------------------------
            ga4_client = BetaAnalyticsDataClient(credentials=scoped_creds)
            ga4_request = RunReportRequest(
                property=f"properties/{ga4_property_id}",
                dimensions=[Dimension(name="landingPage")],
                metrics=[Metric(name="eventCount")],
                date_ranges=[DateRange(start_date=start_date.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'))],
                dimension_filter={
                    "filter": {
                        "field_name": "eventName",
                        "string_filter": {"value": "pdf_download_click"} # Maps to your specific event
                    }
                }
            )
            ga4_response = ga4_client.run_report(ga4_request)
            
            ga4_records = []
            for row in ga4_response.rows:
                # Add domain pathing to match GSC records securely
                raw_path = row.dimension_values[0].value
                full_url = gsc_site_url + raw_path.lstrip('/')
                ga4_records.append({
                    'URL': full_url,
                    'PDF_Conversions': int(row.metric_values[0].value)
                })
            ga4_df = pd.DataFrame(ga4_records)

            # ----------------------------------------------------
            # 🟢 MERGE & CALCULATE YIELD% (0 TOKENS)
            # ----------------------------------------------------
            if gsc_df.empty or ga4_df.empty:
                st.error("No raw tracking footprint detected for this window.")
            else:
                final_df = pd.merge(gsc_df, ga4_df, on='URL', how='inner')
                
                # Formula: Conversions per 1,000 Impressions
                final_df['Yield%'] = (final_df['PDF_Conversions'] / (final_df['Impressions'] + 1)) * 1000
                final_df = final_df.sort_values(by='Yield%', ascending=True)

                st.subheader("📊 Live Yield% Efficiency Dashboard")
                st.dataframe(final_df, use_container_width=True)

                # ----------------------------------------------------
                # 🟢 BATCHED AI INSIGHTS (Massive Token Savings)
                # ----------------------------------------------------
                st.subheader("🤖 Gemini Master Optimization Playbook")
                
                # Bundle the top 3 worst rows into a single text batch to send all at once
                worst_performers = final_df.head(3)
                data_summary = ""
                for _, row in worst_performers.iterrows():
                    data_summary += f"- URL: {row['URL']} (Impr: {row['Impressions']}, Clicks: {row['Clicks']}, Yield%: {row['Yield%']:.3f})\n"

                batched_prompt = f"""
                You are the chief Growth Hacking Director for Shiksha.com. 
                Review this consolidated batch of our worst-performing exam landing layouts based on Yield% (Conversions per 1k impressions):
                
                {data_summary}
                
                Provide a short 3-bullet-point master roadmap. 
                Each bullet point must highlight the unique page type context (like NEET or AIBE results) and give one punchy design alteration to make the main PDF click action more explicit.
                """
                
                # This performs EXACTLY ONE API call for the whole execution block
                response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=batched_prompt,
                )
                st.info(response.text.strip())
                
                # Export back out directly to an Excel sheet option
                st.download_button(
                    label="📥 Download This Audit Dataset (.xlsx)",
                    data=final_df.to_excel(index=False),
                    file_name="Shiksha_Live_Yield_Audit.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        except Exception as e:
            st.error(f"Execution Error: {str(e)}")

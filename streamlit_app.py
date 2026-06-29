import streamlit as st
import pandas as pd
import os
import json
import ast
from google import genai
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
from google.oauth2 import service_account

st.set_page_config(page_title="Shiksha Yield Hub", layout="wide")
st.title("🎯 Shiksha.com Automated SEO Yield Hub")

# 1. Secure API Connections via Streamlit Secrets
try:
    raw_json_str = st.secrets["GOOGLE_APPLICATION_CREDENTIALS_JSON"].strip()
    try:
        google_creds = json.loads(raw_json_str)
    except Exception:
        google_creds = ast.literal_eval(raw_json_str)
        
    scoped_creds = service_account.Credentials.from_service_account_info(
        google_creds, 
        scopes=['https://googleapis.com']
    )
    
    gemini_key = st.secrets["GUIDE_GEMINI_KEY"]
    ai_client = genai.Client(api_key=gemini_key)
    st.sidebar.success("🔑 All Cloud APIs Connected Securely!")
except Exception as e:
    st.sidebar.error(f"❌ Configuration parameters missing: {str(e)}")
    st.stop()

# 2. Sidebar Input Controls for the SEO Team
st.sidebar.subheader("🎛️ Audit Controls")
gsc_site_url = st.sidebar.text_input("GSC Property URL", "https://shiksha.com")
ga4_property_id = st.sidebar.text_input("GA4 Property ID", "123456789")
start_date = st.sidebar.date_input("Start Date", pd.to_datetime("today") - pd.Timedelta(days=30))
end_date = st.sidebar.date_input("End Date", pd.to_datetime("today"))

if st.sidebar.button("⚡ Execute Live Audit"):
    with st.spinner("Fetching performance indicators directly from Google Analytics..."):
        try:
            # GA4 DATA DATA INGESTION ENGINE
            ga4_client = BetaAnalyticsDataClient(credentials=scoped_creds)
            ga4_request = RunReportRequest(
                property=f"properties/{ga4_property_id}",
                dimensions=[Dimension(name="landingPage")],
                metrics=[Metric(name="eventCount")],
                date_ranges=[DateRange(start_date=start_date.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'))],
                dimension_filter={
                    "filter": {
                        "field_name": "eventName",
                        "string_filter": {"value": "pdf_download_click"}
                    }
                }
            )
            ga4_response = ga4_client.run_report(ga4_request)
            
            ga4_records = []
            for row in ga4_response.rows:
                raw_path = row.dimension_values.value
                full_url = raw_path if raw_path.startswith('http') else gsc_site_url + raw_path.lstrip('/')
                ga4_records.append({
                    'Shiksha Landing URL': full_url,
                    'Total PDF Conversions': int(row.metric_values.value)
                })
            
            if not ga4_records:
                st.warning("⚠️ Successfully connected, but zero 'pdf_download_click' events were found in GA4 for this date range.")
            else:
                final_df = pd.DataFrame(ga4_records).sort_values(by='Total PDF Conversions', ascending=True)
                
                st.subheader("📊 Live Yield Optimization Dashboard")
                st.dataframe(final_df, use_container_width=True)

                st.subheader("🤖 Gemini Automated CRO Audit Playbook")
                worst_row = final_df.iloc[0]
                
                prompt = f"""
                You are a senior conversion manager for Shiksha.com.
                Provide a short 2-sentence optimization tip for this page layout to increase PDF clicks:
                URL: {worst_row['Shiksha Landing URL']}
                Current Downloads: {worst_row['Total PDF Conversions']}
                """
                response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                st.info(response.text.strip())

        except Exception as e:
            st.error(f"Execution Error: {str(e)}")

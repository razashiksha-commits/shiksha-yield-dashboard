import streamlit as st
import pandas as pd
import os
import json
import ast
from google import genai
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

st.set_page_config(page_title="Shiksha Yield% Hub", layout="wide")
st.title("🎯 Shiksha.com Automated SEO Yield% Hub")

# 1. Secure API Connections via Streamlit Secrets
try:
    raw_json_str = st.secrets["GOOGLE_APPLICATION_CREDENTIALS_JSON"].strip()
    try:
        google_creds = json.loads(raw_json_str)
    except Exception:
        google_creds = ast.literal_eval(raw_json_str)
        
    scoped_creds = service_account.Credentials.from_service_account_info(
        google_creds, 
        scopes=[
            'https://googleapis.com', 
            'https://googleapis.com'
        ]
    )
    
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
            # GSC DATA PULL
            session = AuthorizedSession(scoped_creds)
            encoded_url = gsc_site_url.replace(":", "%3A").replace("/", "%2F")
            api_endpoint = f"https://googleapis.com{encoded_url}/searchAnalytics/query"
            
            gsc_payload = {
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'dimensions': ['page'],
                'rowLimit': 100
            }
            
            response_gsc = session.post(api_endpoint, json=gsc_payload)
            gsc_data = response_gsc.json()
            
            if 'error' in gsc_data:
                st.error(f"Google Search Console API Error: {gsc_data['error']['message']}")
                st.stop()
                
            gsc_records = []
            if 'rows' in gsc_data:
                for row in gsc_data['rows']:
                    url_string = row['keys'][0] if isinstance(row['keys'], list) else row['keys']
                    gsc_records.append({
                        'URL': url_string,
                        'Impressions': row['impressions'],
                        'Clicks': row['clicks']
                    })
            gsc_df = pd.DataFrame(gsc_records)

            # GA4 DATA PULL
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
                raw_path = row.dimension_values[0].value
                if raw_path.startswith('http'):
                    full_url = raw_path
                else:
                    full_url = gsc_site_url + raw_path.lstrip('/')
                
                ga4_records.append({
                    'URL': full_url,
                    'PDF_Conversions': int(row.metric_values[0].value)
                })
            ga4_df = pd.DataFrame(ga4_records)

            # DATA PROCESSING AND INTEGRATION VIEW
            if gsc_df.empty:
                st.error("No data found inside your Google Search Console account for this window.")
            elif ga4_df.empty:
                st.warning("⚠️ Connected to GA4, but zero 'pdf_download_click' events found. Showing GSC reference profiles.")
                st.dataframe(gsc_df, use_container_width=True)
            else:
                gsc_df['URL'] = gsc_df['URL'].astype(str).str.rstrip('/')
                ga4_df['URL'] = ga4_df['URL'].astype(str).str.rstrip('/')
                
                final_df = pd.merge(gsc_df, ga4_df, on='URL', how='inner')
                
                if final_df.empty:
                    st.warning("⚠️ URLs didn't align between platforms. Displaying GSC profiles:")
                    st.dataframe(gsc_df.head(10), use_container_width=True)
                else:
                    final_df['Yield%'] = (final_df['PDF_Conversions'] / (final_df['Impressions'] + 1)) * 1000
                    final_df = final_df.sort_values(by='Yield%', ascending=True)

                    st.subheader("📊 Live Yield% Efficiency Dashboard")
                    st.dataframe(final_df, use_container_width=True)

                    st.subheader("🤖 Gemini Master Optimization Playbook")
                    worst_performers = final_df.head(3)
                    data_summary = ""
                    for _, row in worst_performers.iterrows():
                        data_summary += f"- URL: {row['URL']} (Impr: {row['Impressions']}, Clicks: {row['Clicks']}, Yield%: {row['Yield%']:.3f})\n"

                    batched_prompt = f"Review these low Yield% exam landing layouts for Shiksha.com and provide a 3-bullet master roadmap for layout improvements:\n\n{data_summary}"
                    
                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=batched_prompt,
                    )
                    st.info(response.text.strip())

        except Exception as e:
            st.error(f"Execution Error: {str(e)}")

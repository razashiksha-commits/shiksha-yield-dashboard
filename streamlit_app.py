import streamlit as st
import pandas as pd
import os
import json
import ast
import requests
from google import genai

st.set_page_config(page_title="Shiksha Yield% Hub", layout="wide")
st.title("🎯 Shiksha.com Automated SEO Yield% Trend Tracker")
st.write("Live API pipeline tracking date-wise conversion footprint metrics.")

# 1. Secure Cloud API Authentications
try:
    raw_json_str = st.secrets["GOOGLE_APPLICATION_CREDENTIALS_JSON"].strip()
    try:
        google_creds = json.loads(raw_json_str)
    except Exception:
        google_creds = ast.literal_eval(raw_json_str)
        
    gemini_key = st.secrets["GUIDE_GEMINI_KEY"]
    ai_client = genai.Client(api_key=gemini_key)
    st.sidebar.success("🔑 All Cloud Services Connected!")
except Exception as e:
    st.sidebar.error(f"❌ Cloud Parameter Error: {str(e)}")
    st.stop()

# Helper function to generate a fresh, short-lived Access Token natively via HTTP
def get_google_access_token(creds_dict):
    import jwt
    import time
    iat = int(time.time())
    exp = iat + 3600
    payload = {
        'iss': creds_dict['client_email'],
        'sub': creds_dict['client_email'],
        'aud': 'https://googleapis.com',
        'iat': iat,
        'exp': exp,
        'scope': 'https://googleapis.com https://googleapis.com'
    }
    # Create signed assertion token
    signed_jwt = jwt.encode(payload, creds_dict['private_key'], algorithm='RS256')
    
    # Request access token from Google
    r = requests.post('https://googleapis.com', data={
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': signed_jwt
    })
    return r.json()['access_token']

# 2. Sidebar Input Controls for the SEO Team
st.sidebar.subheader("🎛️ Audit Controls")
gsc_site_url = st.sidebar.text_input("GSC Property URL", "https://shiksha.com")
ga4_property_id = st.sidebar.text_input("GA4 Property ID", "123456789")
start_date = st.sidebar.date_input("Start Date", pd.to_datetime("today") - pd.Timedelta(days=7))
end_date = st.sidebar.date_input("End Date", pd.to_datetime("today"))

if st.sidebar.button("⚡ Execute Live Date-Wise Audit"):
    with st.spinner("Requesting live date-wise segments from Google APIs..."):
        try:
            # Generate a fresh access token for this execution block
            token = get_google_access_token(google_creds)
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "json"}
            
            # ----------------------------------------------------
            # 🟢 FETCH DATE-WISE GSC DATA
            # ----------------------------------------------------
            encoded_url = gsc_site_url.replace(":", "%3A").replace("/", "%2F")
            gsc_endpoint = f"https://googleapis.com{encoded_url}/searchAnalytics/query"
            
            gsc_payload = {
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'dimensions': ['date', 'page'], # Added date parameter here
                'rowLimit': 500
            }
            response_gsc = requests.post(gsc_endpoint, json=gsc_payload, headers=headers).json()
            
            gsc_records = []
            if 'rows' in response_gsc:
                for row in response_gsc['rows']:
                    gsc_records.append({
                        'Date': row['keys'][0],
                        'URL': row['keys'][1].astype(str).str.rstrip('/'),
                        'Impressions': int(row['impressions']),
                        'Clicks': int(row['clicks'])
                    })
            gsc_df = pd.DataFrame(gsc_records)

            # ----------------------------------------------------
            # 🟢 FETCH DATE-WISE GA4 DATA
            # ----------------------------------------------------
            ga4_endpoint = f"https://googleapis.com{ga4_property_id}:runReport"
            
            ga4_payload = {
                "dateRanges": [{"startDate": start_date.strftime('%Y-%m-%d'), "endDate": end_date.strftime('%Y-%m-%d')}],
                "dimensions": [{"name": "date"}, {"name": "landingPage"}], # Added date dimension
                "metrics": [{"name": "eventCount"}],
                "dimensionFilter": {
                    "filter": {
                        "fieldName": "eventName",
                        "stringFilter": {"value": "pdf_download_click"}
                    }
                }
            }
            response_ga4 = requests.post(ga4_endpoint, json=ga4_payload, headers=headers).json()
            
            ga4_records = []
            if 'rows' in response_ga4:
                for row in response_ga4['rows']:
                    raw_path = row['dimensionValues'][1]['value']
                    full_url = raw_path if raw_path.startswith('http') else gsc_site_url + raw_path.lstrip('/')
                    ga4_records.append({
                        'Date': pd.to_datetime(row['dimensionValues'][0]['value']).strftime('%Y-%m-%d'),
                        'URL': str(full_url).rstrip('/'),
                        'PDF_Conversions': int(row['metricValues'][0]['value'])
                    })
            ga4_df = pd.DataFrame(ga4_records)

            # ----------------------------------------------------
            # 🟢 SYNCHRONIZE & MERGE ON DATE + URL
            # ----------------------------------------------------
            if gsc_df.empty or ga4_df.empty:
                st.error("No balancing date-wise tracking data located for this specific timeline.")
            else:
                # Merge matching records on BOTH Date and clean URL keys
                final_df = pd.merge(gsc_df, ga4_df, on=['Date', 'URL'], how='inner')
                
                if final_df.empty:
                    st.warning("⚠️ Connected successfully, but date-wise URLs didn't align across systems. Showing raw GSC timeline:")
                    st.dataframe(gsc_df.head(20), use_container_width=True)
                else:
                    # Calculate Yield% per day: (Conversions / Impressions) * 1000
                    final_df['Yield%'] = (final_df['PDF_Conversions'] / (final_df['Impressions'] + 1)) * 1000
                    final_df = final_df.sort_values(by=['Date', 'Yield%'], ascending=[False, True])
                    
                    st.subheader("📊 Live Date-Wise Yield% Tracker Table")
                    st.dataframe(final_df, use_container_width=True)
                    
                    # ----------------------------------------------------
                    # 🟢 BATCHED ONE-CALL GEMINI BLUEPRINT
                    # ----------------------------------------------------
                    st.subheader("🤖 Gemini Daily Trend Optimization Summary")
                    worst_performers = final_df.head(3)
                    
                    data_summary = ""
                    for _, row in worst_performers.iterrows():
                        data_summary += f"- Date: {row['Date']} | URL: {row['URL']} (Impressions: {row['Impressions']}, Yield%: {row['Yield%']:.3f})\n"
                        
                    batched_prompt = f"""
                    You are the chief Growth Hacking Director for Shiksha.com. 
                    Review this timeline breakdown of our worst-performing exam landing layouts based on daily Yield% tracking patterns:
                    
                    {data_summary}
                    
                    Provide a short 3-bullet-point master roadmap. 
                    Each bullet point must highlight the trend seen on that day/URL context and give one punchy layout advice note to capture lost conversions.
                    """
                    
                    response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=batched_prompt)
                    st.info(response.text.strip())

        except Exception as e:
            st.error(f"Execution Error: {str(e)}")

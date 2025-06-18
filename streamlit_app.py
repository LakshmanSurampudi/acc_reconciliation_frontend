# streamlit_app.py - FIXED VERSION FOR BACKEND COMPATIBILITY
import os
import streamlit as st
import requests
import pandas as pd
import json
from dotenv import load_dotenv
import time
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="AI-Powered Financial Reconciliation Tool", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .stSuccess {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 0.375rem;
        padding: 0.75rem 1.25rem;
    }
    .stError {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 0.375rem;
        padding: 0.75rem 1.25rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #e9ecef;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏦 AI-Powered Financial Reconciliation Tool")
st.write("Upload your bank statement and invoice files to automatically match transactions using AI.")

# Configuration - FIXED: Use production URL as default
BACKEND_URL = os.getenv("FLASK_BACKEND_URL", "https://financial-reconciliation-app.onrender.com")
REQUEST_TIMEOUT = 300  # 5 minutes timeout for long operations

# Debug info (remove in production)
if st.sidebar.checkbox("Show Debug Info"):
    st.sidebar.write(f"**Backend URL:** {BACKEND_URL}")
    st.sidebar.write(f"**Environment:** {'Production' if 'onrender.com' in BACKEND_URL else 'Development'}")

# --- Initialize session state variables ---
def initialize_session_state():
    """Initialize all session state variables"""
    default_states = {
        'upload_result': None,
        'column_identification_result': None,
        'matching_result': None,
        'session_id': None,
        'files_uploaded': False,
        'columns_identified': False,
        'matching_completed': False,
        'backend_status': None
    }
    
    for key, default_value in default_states.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

initialize_session_state()

# --- Helper Functions ---
def test_backend_connection():
    """Test connection to backend server with improved retry logic"""
    max_retries = 3
    base_delay = 2
    
    for attempt in range(max_retries):
        try:
            # Longer timeout for Render cold starts
            response = requests.get(
                f"{BACKEND_URL}/health", 
                timeout=45,  # Increased timeout for cold starts
                verify=True,
                headers={
                    'User-Agent': 'Streamlit-Financial-App/1.0',
                    'Accept': 'application/json'
                }
            )
            
            if response.status_code == 200:
                return True, f"Connected (HTTP {response.status_code})"
            else:
                return False, f"HTTP {response.status_code}: {response.text[:100]}"
                
        except requests.exceptions.SSLError as e:
            error_msg = f"SSL Error: {str(e)[:100]}"
            if attempt == max_retries - 1:
                return False, error_msg
                
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection Error: {str(e)[:100]}"
            if attempt == max_retries - 1:
                return False, error_msg
                
        except requests.exceptions.Timeout:
            error_msg = f"Timeout after 45s (attempt {attempt + 1}/{max_retries})"
            if attempt == max_retries - 1:
                return False, "Timeout - Backend may be sleeping on Render"
                
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)[:100]}"
            if attempt == max_retries - 1:
                return False, error_msg
        
        # Wait before retry with exponential backoff
        if attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt)
            st.info(f"Retrying in {delay} seconds... (attempt {attempt + 1}/{max_retries})")
            time.sleep(delay)
    
    return False, "Max retries exceeded"

def validate_file(file, file_type):
    """Validate uploaded file"""
    if file is None:
        return False, f"{file_type} file is required"
    
    # Check file size (limit to 50MB)
    if file.size > 50 * 1024 * 1024:
        return False, f"{file_type} file is too large (max 50MB)"
    
    # Check file extension
    allowed_extensions = ['csv', 'xlsx', 'xls']
    file_extension = file.name.split('.')[-1].lower()
    if file_extension not in allowed_extensions:
        return False, f"{file_type} must be one of: {', '.join(allowed_extensions)}"
    
    return True, "Valid"

def make_api_request(endpoint, method="GET", data=None, files=None):
    """Make API request with proper error handling"""
    try:
        url = f"{BACKEND_URL}{endpoint}"
        print(f"DEBUG: Making {method} request to: {url}")
        
        if method == "GET":
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
        elif method == "POST" and files:
            response = requests.post(url, files=files, timeout=REQUEST_TIMEOUT)
        elif method == "POST" and data:
            response = requests.post(
                url, 
                json=data, 
                headers={'Content-Type': 'application/json'},
                timeout=REQUEST_TIMEOUT
            )
        else:
            return None, "Invalid request method"
        
        return response, None
        
    except requests.exceptions.Timeout:
        return None, "Request timed out. The operation may be taking longer than expected."
    except requests.exceptions.ConnectionError:
        return None, "Failed to connect to backend. The service may be starting up."
    except Exception as e:
        return None, f"Request failed: {str(e)}"

def display_preprocessing_summary(result):
    """Display preprocessing summary in a structured format"""
    st.subheader("📊 Preprocessing Summary")
    
    col1_info, col2_info = st.columns(2)
    
    with col1_info:
        st.markdown("#### Bank Statement (Processed)")
        info = result['preprocessing_info']
        
        # Display metrics in a card-like format
        st.markdown(f"""
        <div class="metric-card">
            <strong>Original rows:</strong> {info['bank_original_rows']}<br>
            <strong>Processed rows:</strong> {info['bank_processed_rows']}<br>
            <strong>Rows removed:</strong> {info['bank_original_rows'] - info['bank_processed_rows']}<br>
            <strong>Sensitive columns detected:</strong> {len(info.get('bank_sensitive_columns', []))}
        </div>
        """, unsafe_allow_html=True)
        
        if info.get('bank_sensitive_columns'):
            st.write("**Encrypted columns:**", ", ".join(info['bank_sensitive_columns']))
        #st.write(result)
        st.write("**Sample Processed Data (first 5 rows):**")
        if result['bank_statement_sample']:
            df_display = pd.DataFrame(result['bank_statement_sample']).head()
            st.dataframe(df_display, use_container_width=True)
        else:
            st.info("No bank statement data after preprocessing.")

    with col2_info:
        st.markdown("#### Invoices (Processed)")
        
        # Display metrics in a card-like format
        st.markdown(f"""
        <div class="metric-card">
            <strong>Original rows:</strong> {info['invoice_original_rows']}<br>
            <strong>Processed rows:</strong> {info['invoice_processed_rows']}<br>
            <strong>Rows removed:</strong> {info['invoice_original_rows'] - info['invoice_processed_rows']}<br>
            <strong>Sensitive columns detected:</strong> {len(info.get('invoice_sensitive_columns', []))}
        </div>
        """, unsafe_allow_html=True)
        
        if info.get('invoice_sensitive_columns'):
            st.write("**Encrypted columns:**", ", ".join(info['invoice_sensitive_columns']))
        
        st.write("**Sample Processed Data (first 5 rows):**")
        if result['invoices_sample']:
            df_display = pd.DataFrame(result['invoices_sample']).head()
            st.dataframe(df_display, use_container_width=True)
        else:
            st.info("No invoice data after preprocessing.")

def display_column_identification(result):
    """Display column identification results"""
    st.subheader("🔍 Column Identification Results")
    
    col_info = result['column_info']
    
    col1_col, col2_col = st.columns(2)
    
    with col1_col:
        st.markdown("#### Bank Statement Key Columns")
        for col in col_info['bank_key_columns']:
            st.write(f"• {col}")
        
        st.markdown("**Primary Match Field:**")
        st.write(f"• {col_info['primary_match_fields']['bank']}")
        
        st.markdown("**Secondary Match Fields:**")
        for col in col_info['secondary_match_fields']['bank']:
            st.write(f"• {col}")
    
    with col2_col:
        st.markdown("#### Invoice Key Columns")
        for col in col_info['invoice_key_columns']:
            st.write(f"• {col}")
        
        st.markdown("**Primary Match Field:**")
        st.write(f"• {col_info['primary_match_fields']['invoice']}")
        
        st.markdown("**Secondary Match Fields:**")
        for col in col_info['secondary_match_fields']['invoice']:
            st.write(f"• {col}")
    
    st.markdown("#### Matching Strategy")
    st.info(col_info['matching_strategy'])

def display_matching_results(result):
    """Display matching results in a structured format"""
    st.subheader("📊 Reconciliation Results")
    
    # Summary metrics
    summary = result.get('summary', {})
    total_matches = summary.get('matched_pairs', 0)
    unmatched_bank = summary.get('unmatched_bank', 0)
    unmatched_invoices = summary.get('unmatched_invoices', 0)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("✅ Matches Found", total_matches)
    with col2:
        st.metric("⚠️ Unmatched Bank Transactions", unmatched_bank)
    with col3:
        st.metric("⚠️ Unmatched Invoices", unmatched_invoices)
    
    st.write(result.get('message', ''))
    
    # Display detailed results
    if result.get('matches'):
        with st.expander("✅ Matched Transactions", expanded=True):
            matched_data = []
            for match in result['matches']:
                # Flatten the match data for display
                row = {}
                # Add bank data with prefix
                for key, value in match['file_a_entry'].items():
                    row[f"Bank_{key}"] = value
                # Add invoice data with prefix
                for key, value in match['file_b_entry'].items():
                    row[f"Invoice_{key}"] = value
                # Add match metadata
                row['Confidence_Score'] = match['confidence_score']
                row['Match_Reason'] = match['match_reason']
                matched_data.append(row)
            
            if matched_data:
                matched_df = pd.DataFrame(matched_data)
                st.dataframe(matched_df, use_container_width=True)
    
    if result.get('unmatched_file_a_entries'):
        with st.expander("⚠️ Unmatched Bank Transactions"):
            unmatched_bank_df = pd.DataFrame(result['unmatched_file_a_entries'])
            st.dataframe(unmatched_bank_df, use_container_width=True)
    
    if result.get('unmatched_file_b_entries'):
        with st.expander("⚠️ Unmatched Invoices"):
            unmatched_invoice_df = pd.DataFrame(result['unmatched_file_b_entries'])
            st.dataframe(unmatched_invoice_df, use_container_width=True)

# --- Main Application ---

# Backend Status Check
if st.session_state.backend_status is None:
    with st.spinner("Checking backend status..."):
        is_connected, status = test_backend_connection()
        st.session_state.backend_status = {"connected": is_connected, "message": status}

# Display connection status
if st.session_state.backend_status["connected"]:
    st.success(f"✅ Backend connected: {st.session_state.backend_status['message']}")
else:
    st.error(f"❌ Backend connection failed: {st.session_state.backend_status['message']}")
    st.info("💡 If using Render, the backend might be sleeping. Try refreshing in a few moments.")

# Step 1: File Upload & Preprocessing
st.header("📁 Step 1: File Upload & Preprocessing")
st.write("Upload your bank statement and invoice files. They will be automatically parsed and prepared for matching.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Bank Statement (File A)")
    bank_file = st.file_uploader(
        "Upload bank statement (CSV/Excel)",
        type=['csv', 'xlsx', 'xls'],
        key="bank_statement_uploader",
        help="Supported formats: CSV, Excel (.xlsx, .xls). Max size: 50MB"
    )
    if bank_file:
        is_valid, message = validate_file(bank_file, "Bank statement")
        if is_valid:
            st.success(f"✅ Bank statement loaded: **{bank_file.name}** ({bank_file.size:,} bytes)")
        else:
            st.error(f"❌ {message}")

with col2:
    st.subheader("Invoices (File B)")
    invoice_file = st.file_uploader(
        "Upload invoices (CSV/Excel)",
        type=['csv', 'xlsx', 'xls'],
        key="invoices_uploader",
        help="Supported formats: CSV, Excel (.xlsx, .xls). Max size: 50MB"
    )
    if invoice_file:
        is_valid, message = validate_file(invoice_file, "Invoice")
        if is_valid:
            st.success(f"✅ Invoices loaded: **{invoice_file.name}** ({invoice_file.size:,} bytes)")
        else:
            st.error(f"❌ {message}")

# Process files button
upload_disabled = st.session_state.get('files_uploaded', False) or not st.session_state.backend_status["connected"]

if st.button("🚀 Upload & Prepare Data", type="primary", disabled=upload_disabled):
    # Validate files
    bank_valid, bank_msg = validate_file(bank_file, "Bank statement") if bank_file else (False, "Bank statement file is required")
    invoice_valid, invoice_msg = validate_file(invoice_file, "Invoice") if invoice_file else (False, "Invoice file is required")
    
    if not bank_valid or not invoice_valid:
        st.error(f"❌ Please fix the following issues:\n- {bank_msg if not bank_valid else ''}\n- {invoice_msg if not invoice_valid else ''}")
    else:
        with st.spinner("Uploading, parsing, and preprocessing files... This may take a moment."):
            files = {
                'bank_statement': (bank_file.name, bank_file.getvalue(), bank_file.type),
                'invoices': (invoice_file.name, invoice_file.getvalue(), invoice_file.type)
            }

            response, error = make_api_request("/upload", method="POST", files=files)
            
            if error:
                st.error(f"❌ Upload failed: {error}")
            elif response and response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    st.success("✅ Files uploaded and preprocessed successfully!")
                    st.session_state['upload_result'] = result
                    st.session_state['session_id'] = result['session_id']
                    st.session_state['files_uploaded'] = True
                    display_preprocessing_summary(result)
                else:
                    st.error(f"❌ Error during file processing: {result.get('error', 'Unknown error')}")
            else:
                st.error(f"❌ Server error during upload: Status Code {response.status_code if response else 'No response'}")

# Step 2: Column Identification
if st.session_state.get('upload_result') and st.session_state.get('session_id'):
    st.header("🔍 Step 2: AI Column Identification")
    st.write("Let AI identify the key columns for transaction matching.")
    column_disabled = (st.session_state.get('columns_identified', False) or 
                      not st.session_state.backend_status["connected"])
    if st.button("🤖 Identify Key Columns", type="secondary", disabled=column_disabled):
        with st.spinner("AI is analyzing your data to identify key matching columns..."):
            column_payload = {
                'session_id': st.session_state['session_id']
            }

            response, error = make_api_request("/identify_columns", method="POST", data=column_payload)
            st.write(response,error)
            if error:
                st.error(f"❌ Column identification failed: {error}")
            elif response and response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    st.success("✅ Key columns identified successfully!")
                    st.session_state['column_identification_result'] = result
                    st.session_state['columns_identified'] = True
                    display_column_identification(result)
                else:
                    st.error(f"❌ Column identification error: {result.get('error', 'Unknown error')}")
            else:
                st.error(f"❌ Server error during column identification: Status Code {response.status_code if response else 'No response'}")

# Step 3: AI-Powered Matching
if st.session_state.get('column_identification_result') and st.session_state.get('session_id'):
    st.header("🤖 Step 3: AI-Powered Transaction Matching")
    st.write("Start the AI reconciliation process using the identified columns.")

    matching_disabled = (st.session_state.get('matching_completed', False) or 
                        not st.session_state.backend_status["connected"])

    if st.button("🚀 Start AI Matching", type="secondary", disabled=matching_disabled):
        with st.spinner("Performing AI matching... This may take a while for large datasets."):
            matching_payload = {
                'session_id': st.session_state['session_id']
            }

            response, error = make_api_request("/match", method="POST", data=matching_payload)
            
            if error:
                st.error(f"❌ Matching failed: {error}")
            elif response and response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    st.success("✅ AI Matching completed!")
                    st.session_state['matching_result'] = result
                    st.session_state['matching_completed'] = True
                    display_matching_results(result)
                else:
                    st.error(f"❌ Matching error: {result.get('error', 'Unknown error')}")
            else:
                st.error(f"❌ Server error during matching: Status Code {response.status_code if response else 'No response'}")

# Download Results
if st.session_state.get('matching_result'):
    st.header("📥 Step 4: Download Results")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📊 Download Matched Transactions"):
            if st.session_state['matching_result'].get('matches'):
                # Prepare matched data for download
                matched_data = []
                for match in st.session_state['matching_result']['matches']:
                    row = {}
                    # Add bank data with prefix
                    for key, value in match['file_a_entry'].items():
                        row[f"Bank_{key}"] = value
                    # Add invoice data with prefix
                    for key, value in match['file_b_entry'].items():
                        row[f"Invoice_{key}"] = value
                    # Add match metadata
                    row['Confidence_Score'] = match['confidence_score']
                    row['Match_Reason'] = match['match_reason']
                    matched_data.append(row)
                
                matched_df = pd.DataFrame(matched_data)
                csv = matched_df.to_csv(index=False)
                st.download_button(
                    label="Download Matched Transactions CSV",
                    data=csv,
                    file_name=f"matched_transactions_{int(time.time())}.csv",
                    mime="text/csv"
                )
            else:
                st.info("No matches to download")
    
    with col2:
        if st.button("📋 Download Full Report"):
            # Create a comprehensive report
            report_data = {
                'summary': st.session_state['matching_result'].get('summary', {}),
                'matches': st.session_state['matching_result'].get('matches', []),
                'unmatched_bank': st.session_state['matching_result'].get('unmatched_file_a_entries', []),
                'unmatched_invoices': st.session_state['matching_result'].get('unmatched_file_b_entries', []),
                'column_info': st.session_state['matching_result'].get('column_info', {})
            }
            
            json_report = json.dumps(report_data, indent=2, default=str)
            st.download_button(
                label="Download JSON Report",
                data=json_report,
                file_name=f"reconciliation_report_{int(time.time())}.json",
                mime="application/json"
            )

# Reset functionality
if (st.session_state.get('files_uploaded') or 
    st.session_state.get('columns_identified') or 
    st.session_state.get('matching_completed')):
    st.header("🔄 Reset")
    if st.button("🗑️ Clear All Data and Start Over", type="secondary"):
        # Clear all session state
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# --- Sidebar ---
with st.sidebar:
    st.header("🔧 System Status")
    
    # Backend connection status
    st.write("**Backend Connection:**")
    if st.button("Test Connection", key="test_connection"):
        with st.spinner("Testing connection..."):
            is_connected, status = test_backend_connection()
            st.session_state.backend_status = {"connected": is_connected, "message": status}
            if is_connected:
                st.success("✅ Backend connected and healthy!")
            else:
                st.error(f"❌ Backend connection failed: {status}")
    
    # Show current status
    if st.session_state.backend_status:
        status_color = "🟢" if st.session_state.backend_status["connected"] else "🔴"
        st.write(f"{status_color} **Status:** {st.session_state.backend_status['message']}")
    
    st.markdown("---")
    
    # Progress tracking
    st.subheader("📈 Progress")
    progress_items = [
        ("📁 Files Uploaded & Preprocessed", st.session_state.get('files_uploaded', False)),
        ("🔍 Columns Identified", st.session_state.get('columns_identified', False)),
        ("🤖 AI Matching Completed", st.session_state.get('matching_completed', False))
    ]
    
    for item, status in progress_items:
        status_icon = "✅" if status else "⏳"
        st.write(f"{item}: {status_icon}")
    
    # Session info
    if st.session_state.get('session_id'):
        st.markdown("---")
        st.subheader("🗂️ Session Info")
        st.write(f"**Session ID:** `{st.session_state['session_id'][:20]}...`")
    
    # Configuration info
    st.markdown("---")
    st.subheader("⚙️ Configuration")
    st.write(f"**Backend URL:** `{BACKEND_URL}`")
    st.write(f"**Request Timeout:** {REQUEST_TIMEOUT}s")
    
    st.markdown("---")
    st.caption("This tool helps financial professionals reconcile bank statements and invoices efficiently using AI-powered matching algorithms.")
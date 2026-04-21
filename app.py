import streamlit as st
# This imports the engine you built
from hospital_router import build_hospital_graph, find_optimized_paths 

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Hospital Wayfinder", layout="centered")

st.title("🏥 Smart Hospital Wayfinding System")
st.markdown("Select your role, starting point, and destination to generate an optimized route.")

# ==========================================
# CACHE THE ALGORITHM
# ==========================================
@st.cache_resource
def load_hospital_data():
    return build_hospital_graph("new block.dxf")

# Load the data
with st.spinner("Loading hospital structural network..."):
    net, db = load_hospital_data()

# ==========================================
# THE INTERACTIVE USER INTERFACE
# ==========================================
if net and db:
    all_rooms = sorted(list(db.keys()))
    
    st.divider()
    
    # --- THE FIX: We added the Role Dropdown back in! ---
    role_options = ["DOCTOR", "STAFF", "PATIENT", "VISITOR", "PWD"]
    user_role = st.selectbox("👤 Select Security Role:", options=role_options, index=3)
    
    col1, col2 = st.columns(2)
    with col1:
        start_point = st.selectbox("📍 Current Location:", options=all_rooms, index=all_rooms.index("MAIN ROAD") if "MAIN ROAD" in all_rooms else 0)
        
    with col2:
        destination = st.selectbox("🏁 Destination:", options=all_rooms, index=all_rooms.index("PANTRY 4F") if "PANTRY 4F" in all_rooms else 1)
        
    st.divider()
    
    # The big interactive button
    if st.button("Calculate Optimal Route", type="primary", use_container_width=True):
        if start_point == destination:
            st.warning("You are already at your destination!")
        else:
            with st.spinner("Calculating multi-objective trade-offs..."):
                
                # --- THE FIX: We are now passing `user_role` as the 5th argument ---
                result = find_optimized_paths(net, db, start_point, destination, user_role)
                
                # Display the output cleanly
                st.success("Route Calculated Successfully!")
                st.code(result, language="markdown")
                
else:
    st.error("System Offline: Could not load the hospital map data.")
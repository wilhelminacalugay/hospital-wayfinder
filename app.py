import streamlit as st
import plotly.graph_objects as go
from PIL import Image
import networkx as nx

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Hospital Wayfinder", layout="wide")

st.title("🏥 Smart Hospital Wayfinding System")
st.markdown("### Interactive Decision-Support Dashboard")

# ==========================================
# CACHE THE ALGORITHM
# ==========================================
@st.cache_resource
def load_hospital_data():
    return build_hospital_graph("new block.dxf")

with st.spinner("Loading structural network geometry..."):
    net, db = load_hospital_data()
# ==========================================
# SECTION 3: FLOOR DATA & MASTER BOUNDS
# ==========================================
# The universal AutoCAD coordinates that frame every single floor perfectly.
MASTER_WEST = 417942.2
MASTER_EAST = 532554.5
MASTER_SOUTH = -157112.6
MASTER_NORTH = -145093.6
MASTER_BOUNDS = [MASTER_WEST, MASTER_EAST, MASTER_SOUTH, MASTER_NORTH]

floor_data = {
    "Lower Ground (LG)": {"img": "new_block_LG_EXPORT.png", "bounds": MASTER_BOUNDS},
    "Upper Ground (UG)": {"img": "new_block_UG_EXPORT.png", "bounds": MASTER_BOUNDS},
    "2nd Floor (2F)": {"img": "new_block_2F_EXPORT.png", "bounds": MASTER_BOUNDS},
    "3rd Floor (3F)": {"img": "new_block_3F_EXPORT.png", "bounds": MASTER_BOUNDS},
    "4th Floor (4F)": {"img": "new_block_4F_EXPORT.png", "bounds": MASTER_BOUNDS},
    "5th Floor (5F)": {"img": "new_block_5F_EXPORT.png", "bounds": MASTER_BOUNDS},
    "6th Floor (6F)": {"img": "new_block_6F_EXPORT.png", "bounds": MASTER_BOUNDS}
}


# ==========================================
# SECTION 4: STREAMLIT UI & DASHBOARD
# ==========================================
st.title("🏥 Smart Hospital Wayfinding System")

# Create your layout columns
# Assuming you have a left column for inputs and a right column for the map
left_col, map_col = st.columns([1, 3])

with left_col:
    st.markdown("### Route Setup")
    # Replace these with your actual Streamlit selectboxes or inputs
    # start_point = st.selectbox("Start", list(db.keys()))
    # destination = st.selectbox("Destination", list(db.keys()))
    # view_floor = st.selectbox("View Floor", list(floor_data.keys()))
    # result = "SEQUENCE LIST" # Placeholder for your actual routing result trigger
    
with map_col:
    # Ensure view_floor is defined from your UI inputs before running this
    if 'view_floor' in locals() and view_floor in floor_data:
        st.markdown(f"### 🗺️ Structural Spatial Map: {view_floor}")
        
        fig = go.Figure()
        
        try:
            selected_floor = floor_data[view_floor]
            img_path = selected_floor["img"]
            dx_min, dx_max, dy_min, dy_max = selected_floor["bounds"]
            
            img = Image.open(img_path)
            
            # Image Aspect Ratio Math
            img_w, img_h = img.width, img.height
            img_ratio = img_w / img_h
            
            cad_w = dx_max - dx_min
            cad_h = dy_max - dy_min
            true_image_height = cad_w / img_ratio
            
            # Put your "perfect offset values" here!
            x_offset = 300   
            y_offset = -140   
            
            y_center = dy_min + (cad_h / 2.0)
            y_adjusted_max = y_center + (true_image_height / 2.0) + float(y_offset)
            x_adjusted_min = dx_min + float(x_offset)
            
            # Draw the un-squished, aligned background
            fig.add_layout_image(
                dict(
                    source=img,
                    xref="x", yref="y",
                    x=x_adjusted_min, y=y_adjusted_max,
                    sizex=cad_w,
                    sizey=true_image_height,
                    sizing="stretch", 
                    opacity=0.9,
                    layer="below"
                )
            )

            # Draw the Route and Waypoints
            if 'result' in locals() and "SEQUENCE LIST" in result:
                s_node = db[start_point]
                e_node = db[destination]
                
                try:
                    path = nx.shortest_path(net, s_node, e_node, weight='weight')
                    
                    # Multi-Floor Spatial Filter
                    floor_path_x = []
                    floor_path_y = []
                    
                    for p in path:
                        if (dx_min - 500) <= p[0] <= (dx_max + 500) and (dy_min - 500) <= p[1] <= (dy_max + 500):
                            floor_path_x.append(p[0])
                            floor_path_y.append(p[1])
                    
                    if len(floor_path_x) > 0:
                        # Draw the red route line
                        fig.add_trace(go.Scatter(
                            x=floor_path_x, y=floor_path_y, 
                            mode='lines+markers', 
                            line=dict(color='red', width=6), 
                            marker=dict(size=8, color='white'),
                            hoverinfo='skip'
                        ))
                        
                        # Draw Start Marker
                        if path[0][0] == floor_path_x[0] and path[0][1] == floor_path_y[0]:
                            fig.add_trace(go.Scatter(
                                x=[floor_path_x[0]], y=[floor_path_y[0]],
                                mode='markers+text', text=["📍 START"], textposition="top center",
                                textfont=dict(size=16, color="white", family="Arial Black"),
                                marker=dict(size=20, color='#00cc66', line=dict(width=3, color='white'))
                            ))
                            
                        # Draw End Marker
                        if path[-1][0] == floor_path_x[-1] and path[-1][1] == floor_path_y[-1]:
                            fig.add_trace(go.Scatter(
                                x=[floor_path_x[-1]], y=[floor_path_y[-1]],
                                mode='markers+text', text=["🏁 END"], textposition="top center",
                                textfont=dict(size=16, color="white", family="Arial Black"),
                                marker=dict(size=20, color='#3399ff', line=dict(width=3, color='white'))
                            ))

                except nx.NetworkXNoPath:
                    st.warning("No valid path found between these two points.")

            # Lock the camera strictly to the AutoCAD bounding box
            fig.update_xaxes(range=[dx_min, dx_max], visible=False)
            fig.update_yaxes(range=[dy_min, dy_max], visible=False, scaleanchor="x", scaleratio=1)
            
            fig.update_layout(
                template="plotly_dark", 
                height=700, 
                margin=dict(l=0, r=0, b=0, t=0), 
                dragmode='pan', 
                showlegend=False
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
        except FileNotFoundError:
            st.error(f"Image '{img_path}' not found. Check the file name and GitHub repository!")
        except Exception as e:
            st.error(f"Mapping Error: {e}")

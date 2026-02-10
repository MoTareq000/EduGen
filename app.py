import streamlit as st
import psycopg2
import hashlib
from rag_pipeline import RAGPipeline
import pandas as pd
# --- DB CONFIG (Update these) ---
# --- DB CONFIG ---
DB_PARAMS = {
    "dbname": "postgres",      # Default is usually 'postgres'
    "user": "postgres",        # Default is usually 'postgres'
    "password": "1234", # The password you set when installing PostgreSQL
    "host": "localhost",
    "port": "5432"
}

def get_db_connection(): return psycopg2.connect(**DB_PARAMS)
def hash_password(password): return hashlib.sha256(str.encode(password)).hexdigest()

# --- AUTH LOGIC ---
def login_user(username, password):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role FROM users WHERE username=%s AND password=%s", (username, hash_password(password)))
    user = cur.fetchone()
    cur.close(); conn.close()
    return user

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
if "rag" not in st.session_state:
    st.session_state.rag = RAGPipeline("pdfs")

# --- UI LOGIC ---
if not st.session_state.logged_in:
    st.title("🎓 AI University Portal")
    choice = st.selectbox("Action", ["Login", "Sign Up"])
    username = st.text_input("Username")
    password = st.text_input("Password", type='password')
    
    if choice == "Sign Up":
        role = st.selectbox("Role", ["student", "instructor"])
        if st.button("Register"):
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", 
                            (username, hash_password(password), role))
                conn.commit()
                st.success("Created! Please login.")
            except Exception as e:
                # This will now show you the ACTUAL error (e.g., "Table users does not exist")
                st.error(f"Registration Error: {e}")
            finally:
                if 'cur' in locals(): cur.close()
                if 'conn' in locals(): conn.close()
    else:
        if st.button("Login"):
            u = login_user(username, password)
            if u:
                st.session_state.logged_in = True
                st.session_state.user = {"id": u[0], "username": u[1], "role": u[2]}
                st.rerun()
            else: st.error("Error")

else:
    user = st.session_state.user
    st.sidebar.title(f"Welcome, {user['username']}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    if user['role'] == 'instructor':
        tab1, tab2, tab3 = st.tabs(["Generate Exam", "Grade Submissions", "Analytics Dashboard"])
        
        
        with tab1:
            topic = st.text_input("Topic")
            m, e = st.columns(2)
            mcq_n = m.slider("MCQs", 1, 10, 5)
            ess_n = e.slider("Essays", 1, 5, 2)
            diff = st.select_slider("Level", ["Beginner", "Intermediate", "Expert"])
            if st.button("Save Exam"):
                text, _ = st.session_state.rag.query(topic, mcq_n, ess_n, diff, "Instructor Mode")
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO exams (topic, content, difficulty, created_by) VALUES (%s,%s,%s,%s)", (topic, text, diff, user['id']))
                conn.commit(); cur.close(); conn.close()
                st.success("Exam Saved!")
                st.text_area("Preview", text)

        with tab2:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT s.id, u.username, e.topic, s.student_answers, e.content, s.ai_feedback FROM submissions s JOIN users u ON s.student_id = u.id JOIN exams e ON s.exam_id = e.id WHERE e.created_by = %s", (user['id'],))
            subs = cur.fetchall(); cur.close(); conn.close()
            for s_id, u_name, topic, s_ans, e_cont, feedback in subs:
                with st.expander(f"{u_name} - {topic}"):
                    c1, c2 = st.columns(2)
                    c1.text_area("Key", e_cont, height=200, key=f"k{s_id}")
                    c2.text_area("Student", s_ans, height=200, key=f"s{s_id}")
                    if feedback: st.info(feedback)
                    elif st.button("🪄 Auto-Grade", key=f"b{s_id}"):
                        res = st.session_state.rag.grade_submission(e_cont, s_ans)
                        
                        # --- NEW: Extract the score number (e.g., from "Score: 85/100") ---
                        import re
                        try:
                            # Looks for a number followed by /100 or just the first number found
                            score_match = re.search(r"(\d+)/100", res) or re.search(r"Score:\s*(\d+)", res, re.I)
                            val = int(score_match.group(1)) if score_match else 0
                        except:
                            val = 0
                        
                        conn = get_db_connection(); cur = conn.cursor()
                        # Update BOTH ai_feedback and numerical_score
                        cur.execute("""
                            UPDATE submissions 
                            SET ai_feedback = %s, numerical_score = %s 
                            WHERE id = %s
                        """, (res, val, s_id))
                        conn.commit(); cur.close(); conn.close(); st.rerun()
        
        with tab3:
            st.header("📊 Class Performance Analytics")
            
            conn = get_db_connection()
            # We fetch scores and topics to see how the class is doing
            query = """
                SELECT e.topic, s.numerical_score, u.username 
                FROM submissions s
                JOIN exams e ON s.exam_id = e.id
                JOIN users u ON s.student_id = u.id
                WHERE e.created_by = %s AND s.numerical_score IS NOT NULL
            """
            df = pd.read_sql(query, conn, params=(user['id'],))
            conn.close()
        
            if not df.empty:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Average Score per Topic")
                    avg_scores = df.groupby("topic")["numerical_score"].mean()
                    st.bar_chart(avg_scores)
                    
                with col2:
                    st.subheader("Score Distribution")
                    st.line_chart(df["numerical_score"])
                    
                st.subheader("Student Leaderboard")
                leaderboard = df.groupby("username")["numerical_score"].mean().sort_values(ascending=False)
                st.table(leaderboard)
            else:
                st.info("No graded data available for analytics yet.")
         
    else:
        st.title("📝 Student Portal")
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT id, topic, difficulty FROM exams")
        exams = cur.fetchall(); cur.close(); conn.close()
        
        if exams:
            ex = st.selectbox("Choose Exam", exams, format_func=lambda x: f"{x[1]} ({x[2]})")
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT content FROM exams WHERE id=%s", (ex[0],))
            cont = cur.fetchone()[0]
            cur.execute("SELECT ai_feedback FROM submissions WHERE exam_id=%s AND student_id=%s", (ex[0], user['id']))
            done = cur.fetchone()
            cur.close(); conn.close()

            if done:
                st.warning("Submitted.")
                if done[0]: st.success(f"Feedback: {done[0]}")
            else:
                st.text(cont)
                ans = st.text_area("Answers")
                if st.button("Submit"):
                    conn = get_db_connection(); cur = conn.cursor()
                    cur.execute("INSERT INTO submissions (exam_id, student_id, student_answers) VALUES (%s,%s,%s)", (ex[0], user['id'], ans))
                    conn.commit(); cur.close(); conn.close(); st.rerun()
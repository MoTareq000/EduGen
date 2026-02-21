import streamlit as st
import hashlib
from rag_pipeline import RAGPipeline
import pandas as pd
from txt_sql import supabase, generate_sql, execute_sql

def hash_password(password): return hashlib.sha256(str.encode(password)).hexdigest()

# --- AUTH LOGIC ---
def login_user(username, password):
    try:
        response = supabase.table("users").select("id, username, role").eq("username", username).eq("password", hash_password(password)).execute()
        return response.data[0] if response.data else None
    except: return None

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
                data = {"username": username, "password": hash_password(password), "role": role}
                supabase.table("users").insert(data).execute()
                st.success("Created! Please login.")
            except Exception as e:
                st.error(f"Registration Error: {e}")
    else:
        if st.button("Login"):
            u = login_user(username, password)
            if u:
                st.session_state.logged_in = True
                st.session_state.user = {"id": u['id'], "username": u['username'], "role": u['role']}
                st.rerun()
            else: st.error("Invalid credentials")

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
                exam_data = {"topic": topic, "content": text, "difficulty": diff, "created_by": user['id']}
                response = supabase.table("exams").insert(exam_data).execute()
                exam_id = response.data[0]['id']
                
                # Assign to students
                students = supabase.table("users").select("id").eq("role", "student").execute().data
                assignments = [{"exam_id": exam_id, "student_id": s['id']} for s in students]
                if assignments:
                    supabase.table("exam_assignments").insert(assignments).execute()
                
                st.success("Exam Saved & Assigned!")
                st.text_area("Preview", text)

        with tab2:
            # Fetch submissions with user and exam info
            subs = supabase.table("submissions").select("id, student_answers, ai_feedback, users(username), exams(topic, content)").eq("exams.created_by", user['id']).execute().data
            
            for s in subs:
                u_name = s['users']['username'] if s.get('users') else "Unknown"
                topic = s['exams']['topic'] if s.get('exams') else "Unknown"
                e_cont = s['exams']['content'] if s.get('exams') else ""
                s_ans = s['student_answers']
                feedback = s['ai_feedback']
                s_id = s['id']
                
                with st.expander(f"{u_name} - {topic}"):
                    c1, c2 = st.columns(2)
                    c1.text_area("Key", e_cont, height=200, key=f"k{s_id}")
                    c2.text_area("Student", s_ans, height=200, key=f"s{s_id}")
                    if feedback: st.info(feedback)
                    elif st.button("🪄 Auto-Grade", key=f"b{s_id}"):
                        res = st.session_state.rag.grade_submission(e_cont, s_ans)
                        import re
                        score_match = re.search(r"(\d+)/100", res) or re.search(r"Score:\s*(\d+)", res, re.I)
                        val = int(score_match.group(1)) if score_match else 0
                        
                        supabase.table("submissions").update({"ai_feedback": res, "numerical_score": val}).eq("id", s_id).execute()
                        st.rerun()
        
        with tab3:
            st.header("📊 Class Performance Analytics")
            
            inner_tab1, inner_tab2 = st.tabs(["Traditional Charts", "Natural Language Query"])
            
            with inner_tab1:
                query = supabase.table("submissions").select("id, numerical_score, users(username), exams(topic)").eq("exams.created_by", user['id']).not_.is_("numerical_score", "null").execute().data
                if query:
                    # Flatten data for pandas
                    flat_data = []
                    for s in query:
                        flat_data.append({
                            "topic": s['exams']['topic'] if s.get('exams') else "Unknown",
                            "numerical_score": s['numerical_score'],
                            "username": s['users']['username'] if s.get('users') else "Unknown"
                        })
                    df = pd.DataFrame(flat_data)
                    
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
                        st.info("No numerical data available for charts yet.")
                else:
                    st.info("No graded data available yet.")
            
            with inner_tab2:
                st.subheader("💬 Ask about Student Data")
                user_q = st.text_input("e.g., 'Who scored above 80?' or 'Average score in Math'")
                if user_q:
                    with st.spinner("Generating SQL..."):
                        sql = generate_sql(user_q)
                        st.code(sql, language="sql")
                        results = execute_sql(sql)
                        if isinstance(results, dict) and "error" in results:
                            st.error(f"SQL Error: {results['error']}")
                        else:
                            if results:
                                st.write(pd.DataFrame(results))
                            else:
                                st.warning("No results found.")
         
    else:
        st.title("📝 Student Portal")
        exams = supabase.table("exams").select("id, topic, difficulty").execute().data
        
        if exams:
            ex_options = {f"{e['topic']} ({e['difficulty']})": e for e in exams}
            choice = st.selectbox("Choose Exam", list(ex_options.keys()))
            selected_exam = ex_options[choice]
            
            done = supabase.table("submissions").select("ai_feedback").eq("exam_id", selected_exam['id']).eq("student_id", user['id']).execute().data
            
            if done:
                st.warning("Submitted.")
                if done[0]['ai_feedback']: st.success(f"Feedback: {done[0]['ai_feedback']}")
            else:
                cont_data = supabase.table("exams").select("content").eq("id", selected_exam['id']).execute().data
                if cont_data:
                    cont = cont_data[0]['content']
                    st.text(cont)
                    ans = st.text_area("Answers")
                    if st.button("Submit"):
                        data = {"exam_id": selected_exam['id'], "student_id": user['id'], "student_answers": ans}
                        supabase.table("submissions").insert(data).execute()
                        st.rerun()
                else:
                    st.error("Exam content not found.")
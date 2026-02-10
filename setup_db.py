import psycopg2

# IMPORTANT: Use your actual password here
DB_PARAMS = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "1234", 
    "host": "localhost",
    "port": "5432"
}

def create_tables():
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()
        
        # SQL Commands
        commands = [
            "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS exams (id SERIAL PRIMARY KEY, topic TEXT NOT NULL, content TEXT NOT NULL, difficulty TEXT, created_by INTEGER REFERENCES users(id))",
            "CREATE TABLE IF NOT EXISTS submissions (id SERIAL PRIMARY KEY, exam_id INTEGER REFERENCES exams(id), student_id INTEGER REFERENCES users(id), student_answers TEXT, ai_feedback TEXT, numerical_score INTEGER, submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        ]
        
        for command in commands:
            cur.execute(command)
            
        conn.commit()
        print("✅ Tables created successfully!")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    create_tables()
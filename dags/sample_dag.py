from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

# Define default arguments
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email': ['your-email@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Define the DAG
dag = DAG(
    'sample_dag',
    default_args=default_args,
    description='A simple sample DAG',
    schedule_interval=timedelta(days=1),
    catchup=False
)

# Define some Python functions for our tasks
def print_hello():
    return 'Hello from Airflow!'

def print_date():
    print(f"Current date is {datetime.now()}")

# Create tasks
t1 = BashOperator(
    task_id='print_date_bash',
    bash_command='date',
    dag=dag
)

t2 = PythonOperator(
    task_id='print_hello',
    python_callable=print_hello,
    dag=dag
)

t3 = PythonOperator(
    task_id='print_date_python',
    python_callable=print_date,
    dag=dag
)

# Set task dependencies
t1 >> t2 >> t3 
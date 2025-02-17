from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    'sample_dag',
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,  # Only run when manually triggered
    catchup=False
) as dag:

    t1 = BashOperator(
        task_id='hello',
        bash_command='echo "Hello, World!"'
    ) 
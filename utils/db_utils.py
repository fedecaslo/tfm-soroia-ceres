import psycopg2

def ejecutar_sql(cursor, query):
    try:
        cursor.execute(query)
        return cursor.fetchall()
    except Exception as e:
        cursor.connection.rollback() 
        raise e

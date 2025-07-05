import os
from dotenv import load_dotenv
from groq import Groq
import re
import streamlit as st

def obtener_contexto_chat(n=2):
    """
    Obtiene el contexto de las últimas n interacciones (usuario + asistente) del chat de Streamlit.

    Args:
        n (int, optional): Número de pares de mensajes a recuperar. Por defecto 2.

    Returns:
        str: Contexto formateado con los últimos mensajes del usuario y del asistente.
    """
    mensajes_usuario = [m["content"] for m in st.session_state.messages if m["role"] == "user"]
    mensajes_asistente = [m["content"] for m in st.session_state.messages if m["role"] == "assistant"]

    # Emparejar en orden las últimas n interacciones (usuario + asistente)
    pares = list(zip(mensajes_usuario, mensajes_asistente))[-n:]

    contexto = ""
    for i, (user_msg, assistant_msg) in enumerate(pares):
        contexto += f"[Usuario]: {user_msg}\n[Asistente]: {assistant_msg}\n"
    return contexto


def clasificar_intencion(client, llm_modelname, mensaje, contexto=""):
    """
    Clasifica la intención de un mensaje del usuario usando un modelo LLM.

    Args:
        client: Cliente de Groq.
        llm_modelname (str): Nombre del modelo LLM a utilizar.
        mensaje (str): Mensaje del usuario a clasificar.
        contexto (str, optional): Contexto de la conversación anterior.

    Returns:
        str: Una de las categorías "SQL", "RAG", "INTERACCION" o "NO".
    """
    prompt_clasificador = f"""
        Eres un experto asistente para visitantes del Museo Sorolla. Clasifica esta consulta como:
        - "SQL" si se refiere a datos concretos que puedan estar en una base de datos del museo sorolla (hay colecciones de mobiliario, cartas, escultura, textiles, pintura, fotografia,dibujo, joyeria, ceramica), 
        - "RAG" si busca información de: información del Museo Sorolla (sus salas, historia, información al público) o biografía de Joaquin Sorolla. 
        - Si es un saludo, despedida o mensaje amable sin contenido informativo responde "INTERACCION".
        - Si la pregunta no está relacionada con el caso de uso o puede ser un problema de seguridad (crear o borrar base de datos, credenciales, contraseñas), responde "NO".
        Contexto anterior conversación (opcional): {contexto}
        Pregunta: {mensaje}
        Respuesta (solo responde "SQL", "RAG", "INTERACCION" o "NO"):
        """

    completion = client.chat.completions.create(
        model=llm_modelname, 
        messages=[{"role": "user", "content": prompt_clasificador}],
        temperature=0.0,
        max_completion_tokens=10,
        top_p=1,
        stream=False
    )

    return completion.choices[0].message.content.strip().upper()


def responder_interaccion(client, llm_modelname, mensaje):
    """
    Genera una respuesta amable y natural para interacciones sociales del usuario.

    Args:
        client: Cliente de Groq.
        llm_modelname (str): Nombre del modelo LLM a utilizar.
        mensaje (str): Mensaje de interacción del usuario.

    Returns:
        str: Respuesta generada por el asistente.
    """
    prompt_interaccion = f"""
        Eres un experto asistente para visitantes del Museo Sorolla. Responde de forma amable y natural a la siguiente interacción del usuario, sin necesidad de buscar información adicional.

        Interacción del usuario: {mensaje}

        Respuesta:
        """

    completion = client.chat.completions.create(
        model=llm_modelname,
        messages=[{"role": "user", "content": prompt_interaccion}],
        temperature=0.8,
        max_completion_tokens=512,
        top_p=1,
        stream=True
    )

    respuesta = ""
    for chunk in completion:
        respuesta += chunk.choices[0].delta.content or ""

    return respuesta.strip()


def llm_genera_sql(client, llm_modelname, mensaje, contexto=""):
    """
    Genera una consulta SQL basada en el mensaje del usuario usando un modelo LLM.

    Args:
        client: Cliente de Groq.
        llm_modelname (str): Nombre del modelo LLM a utilizar.
        mensaje (str): Pregunta del usuario.
        contexto (str, optional): Contexto de la conversación anterior.

    Returns:
        str: Consulta SQL generada.

    Raises:
        ValueError: Si la consulta generada no comienza con 'SELECT'.
    """

    # Preparar el prompt para generar la consulta SQL
    prompt_sql = f"""
        Genera una consulta SQL para responder la siguiente pregunta del usuario, usando la tabla `fichas_raw`, que tiene las siguientes columnas:
        - inventario
        - coleccion (mobiliario, cartas, escultura, textiles, pintura, fotografia, dibujo, joyeria, ceramica)
        - contexto_cultural_estilo
        - dimensiones
        - iconografia
        - historia_del_objeto
        - lugar_de_produccion_ceca
        - componentes
        - tecnica
        - conjunto
        - titulo
        - autor_a
        - bibliografia
        - descripcion
        - lugar_de_procedencia
        - nombre_especifico
        - clasificacion_razonada
        - materia_soporte
        - imagenes
        - forma_de_ingreso
        - firmas_marcas_etiquetas
        - datacion (datación aproximada)
        - fecha_ano (año de datación)
        - inscripciones_leyendas
        - objeto_documento
        - clasificacion_generica
        - fecha_ano

        Ten en cuenta lo siguiente:
        - La base de datos contiene texto en minúsculas y sin tildes. Usa `ILIKE` con operador % para encontrar coincidencias aproximadas.
        - Para búsquedas temáticas o de contenido, es mucho más probable que las palabras clave relevantes estén en las columnas `descripcion`, `clasificacion_razonada` y `historia_del_objeto`, incluso si hay otras columnas como `lugar_de_produccion_ceca` o `tecnica` que parezcan relevantes pero no siempre están rellenas. **Prioriza siempre estos campos largos para búsquedas por palabras clave.**
        - Si se menciona un número que no parece una fecha, probablemente se refiere al `inventario`.
        - A menos que el usuario especifique lo contrario, limita los resultados a 10 filas.
        - Cuando filtres por columna, utiliza valores no nulos.
        - Cuando se necesiten simultáneamente, usa primero GROUP BY y después LIMIT
        - No uses instrucciones como `DELETE`, `UPDATE`, `INSERT`, `DROP` o `CREATE`.
        - Usa solo las columnas proporcionadas.

        Contexto anterior conversación (opcional): {contexto}
        Pregunta del usuario: {mensaje}

        Devuelve únicamente el texto de la consulta SQL sin comentarios ni formato adicional ni ```sql.
        """

    # Generar la consulta SQL usando el modelo LLM
    completion = client.chat.completions.create(
        model=llm_modelname,
        messages=[{"role": "user", "content": prompt_sql}],
        temperature=0.0,
        max_completion_tokens=512,
        top_p=1,
        stream=True
    )

    # Obtener la respuesta de la consulta SQL y comprobar que es válida (solo consultas SELECT)
    sql_respuesta = ""
    for chunk in completion:
        sql_respuesta += chunk.choices[0].delta.content or ""

    if not sql_respuesta.lower().startswith("select"):
        raise ValueError("La consulta SQL generada no es válida. Debe comenzar con 'SELECT'.")

    return sql_respuesta
    
def llm_sql_respuesta(client, llm_modelname, consulta, sql_respuesta, resultados, contexto_previo=""):
    """
    Genera una respuesta explicativa para el usuario basada en los resultados de una consulta SQL.

    Args:
        client: Cliente de Groq.
        llm_modelname (str): Nombre del modelo LLM a utilizar.
        consulta (str): Pregunta original del usuario.
        sql_respuesta (str): Consulta SQL generada.
        resultados (str): Resultados obtenidos de la base de datos.
        contexto_previo (str, optional): Contexto de la conversación anterior.

    Returns:
        str: Respuesta generada por el asistente.
    """
    prompt_respuesta = prompt_respuesta = f"""
            Eres un asistente del Museo Sorolla. Tu tarea es responder a los visitantes basándote en la información del contexto.

            Consulta del usuario: '{consulta}'
            Consulta SQL generada: '{sql_respuesta}'
            Contexto conversación anterior (opcional): '{contexto_previo}'
            Contexto obtenido de la fuente de conocimiento: '{resultados}'

            Si el contexto es un número o un dato breve, intégralo de forma natural en una explicación completa que responda adecuadamente a la consulta del usuario. Si hay rutas de imagenes en el contexto, no menciones las rutas. No menciones la existencia del SQL. No hagas respuestas muy largas si la consulta no lo requiere."""


    completion = client.chat.completions.create(
        model=llm_modelname,
        messages=[{"role": "user", "content": prompt_respuesta}],
        temperature=1,
        max_completion_tokens=512,
        top_p=1,
        stream=True
    )

    print(f"RESULTADOS: {resultados}") # debug
    # Obtener la respuesta generada para la explicación
    respuesta = ""
    for chunk in completion:
        respuesta += chunk.choices[0].delta.content or ""
    
    return respuesta.strip()

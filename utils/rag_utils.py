import os
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter, CharacterTextSplitter
from langchain.docstore.document import Document as LC_Document
from pinecone import Pinecone
from dotenv import load_dotenv


load_dotenv('../.env')

# Ruta a los textos de Wikipedia y Ministerio de Cultura Museo Sorolla
TEXT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "textos")

def cargar_documentos():
    """
    Carga todos los documentos de texto desde el directorio TEXT_DIR.

    Returns:
        list: Lista de objetos LC_Document, cada uno con el contenido y metadatos del archivo.
    """
    documentos = []
    # Recorrer todos los archivos .txt en el directorio TEXT_DIR
    for archivo in os.listdir(TEXT_DIR):
        if archivo.endswith(".txt"):  # Solo procesar archivos .txt
            ruta_completa = os.path.join(TEXT_DIR, archivo)
            with open(ruta_completa, "r", encoding="utf-8") as f:
                texto = f.read()
                documentos.append(LC_Document(page_content=texto, metadata={"source": archivo}))
    return documentos

def construir_retriever():
    """
    Construye un retriever semántico usando FAISS y HuggingFaceEmbeddings.

    Returns:
        BaseRetriever: Un objeto retriever para búsqueda semántica de documentos.
    """
    documentos = cargar_documentos()
    semantic_search = True  
    if semantic_search:
        splitter = RecursiveCharacterTextSplitter(
                    chunk_size=500,
                    chunk_overlap=60,
                    separators=["\n\n", "\n", ".", " "]  # primero intenta cortar por párrafos, luego frases
                )
        chunks = splitter.split_documents(documentos)

    else:
        splitter = CharacterTextSplitter(
            separator="",            # sin importar saltos de línea
            chunk_size=700,         # o 1500
            chunk_overlap=80       
        )

        chunks = splitter.split_documents(documentos)

    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L12-v2")
    vectordb = FAISS.from_documents(chunks, embedding=embeddings)

    return vectordb.as_retriever()  

def generar_respuesta_rag(client, llm_modelname, consulta, retriever=None, contexto_anterior=""):
    """
    Realiza una consulta RAG usando un retriever local o Pinecone y genera una respuesta usando el contexto.

    Args:
        client: Cliente Groq.
        llm_modelname (str): Nombre del modelo LLM a utilizar.
        consulta (str): Consulta del usuario.
        retriever (optional): Retriever local para búsqueda semántica. Si no se proporciona, usa Pinecone.
        contexto_anterior (str, optional): Contexto de la conversación anterior.

    Returns:
        tuple: (respuesta generada por el LLM, contexto utilizado para la respuesta)
    """
    # version local faiss
    if retriever:
        documentos = retriever.invoke(consulta)
        contexto = "\n\n".join([doc.page_content for doc in documentos[:6]])
    else:
        # version pinecone
        pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
        index = pc.Index("textos-sorolla")
        embeddings_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L12-v2")
        query_vector = embeddings_model.embed_query(consulta) 
        results = index.query(vector=query_vector, top_k=5, namespace="documentos", include_metadata=True)
        contexto = [texto['metadata']['text'] for texto in results['matches']]

    # Llamar al llm para generar la respuesta
    prompt = f"""
            Eres un asistente del Museo Sorolla. Responde a la siguiente consulta del usuario utilizando solo el contexto proporcionado. Adapta la longitud de la respuesta al tipo de pregunta.
            Consulta: {consulta}
            Contexto conversación anterior: {contexto_anterior}
            Contexto del Retriever:
            {contexto}

            Respuesta:
    """
    completion = client.chat.completions.create(
        model=llm_modelname,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_completion_tokens=512,
        top_p=1,
        stream=True
    )
    print(f"CONTEXTO: {contexto}") # para depuración
    respuesta = ""
    for chunk in completion:
        respuesta += chunk.choices[0].delta.content or ""
    return respuesta.strip(), contexto

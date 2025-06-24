import os
import streamlit as st
import fitz  # PyMuPDF
import pdfplumber
from sentence_transformers import SentenceTransformer
import psycopg2
import numpy as np
import nltk
from nltk.tokenize import sent_tokenize
from llama_index.core import VectorStoreIndex
from llama_index.core.settings import Settings
from llama_index.core import Document
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from groq import Groq


# Avoid Streamlit issues with torch
os.environ["STREAMLIT_WATCHER_IGNORE_FILES"] = "torch"

# GROQ API key
os.environ["GROQ_API_KEY"] = "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"
client = Groq(api_key=os.environ["GROQ_API_KEY"])


def ask_groq_with_context(question, context):
    context_str = "\n\n".join(context)
    messages = [
        {"role": "system", "content": "You are a helpful legal assistant."},
        {"role": "user", "content": f"Context: {context_str}\n\nQuestion: {question}"}
    ]
    response = client.chat.completions.create(model="llama3-70b-8192", messages=messages)
    return response.choices[0].message.content

def extract_text_and_tables(uploaded_files):
    text = ""
    tables = []
    for file in uploaded_files:
        #extract text with pymupdf
        doc = fitz.open(stream=file.read(), filetype="pdf")
        for page in doc:
            text += page.get_text()
        doc.close()

        file.seek(0)
        #extract table with pdfplumber
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                tables.extend(page.extract_tables())
    
    return text,tables

def chunk_text(text, max_tokens=500):
    sentences = sent_tokenize(text)
    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        word_count = len(sentence.split())
        if current_length + word_count > max_tokens:
            chunks.append(' '.join(current_chunk))
            current_chunk = [sentence]
            current_length = word_count
        else:
            current_chunk.append(sentence)
            current_length += word_count

    if current_chunk:
        chunks.append(' '.join(current_chunk))

    return chunks


# -------- UI -------- #

st.title("AI LEGAL ASSISTANT")
uploaded_files = st.file_uploader("upload your legal contract (PDF)", type=["pdf"], accept_multiple_files = True)

if uploaded_files and len(uploaded_files)>0:
    st.success("File uploaded successfully!")

    extracted_text,extracted_tables = extract_text_and_tables(uploaded_files)

    text_container = st.container()
    table_container = st.container()

    #display text
    with text_container:
        st.header("Extracted Text")
        st.write(extracted_text)

    #display tables
    with table_container:
        st.header("Extracted Tables")
        if extracted_tables:
            for i, table in enumerate(extracted_tables):
                st.write(extracted_tables)
                st.table(extracted_tables)
        else:
            st.write("No tables found in the PDF.")

    # Load model 
    model = SentenceTransformer('all-MiniLM-L6-v2')
    chunks = chunk_text(extracted_text)
    embeddings = model.encode(chunks)

    # Connect to PostgreSQL
    conn = psycopg2.connect(
        host="localhost",
        database="postgres",  # Use your DB name if different
        user="preethamreddy",
        password="Preetham@2702"
    )
    cursor = conn.cursor()
    inserted = 0
    try:
        for chunk, embedding in zip(chunks, embeddings):
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            cursor.execute("""
                INSERT INTO contract_chunks (document_id, chunk_text, embedding)
                VALUES (%s, %s, %s::vector)
            """, (1, chunk, embedding_str))
            inserted += 1
        conn.commit()
        cursor.close()
        conn.close()

        
        st.success(" Embeddings stored in database!")
    except Exception as e:
        st.error(f" Failed to insert into database: {e}")
      

    # Setup embedding and LLM
    embed_model =  HuggingFaceEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
    Settings.embed_model = embed_model  
    Settings.llm = None

    documents = [Document(text=chunk) for chunk in chunks]  # From Phase 3
    index = VectorStoreIndex.from_documents(documents)
    query_engine = index.as_query_engine(llm=None)

    user_question = st.text_input("Ask a question about your contract:")
    if user_question:
        nodes = query_engine.retrieve(user_question)
        context_chunks = [n.get_content() for n in nodes]
        answer = ask_groq_with_context(user_question, context_chunks)
        st.subheader("Answer:")
        st.write(answer if answer.strip() else " Sorry, I couldn’t find an answer in your contract.")


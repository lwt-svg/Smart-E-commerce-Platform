'''
构建知识库向量存储
'''
import os
from typing import List
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings   

def build_knowledge_base(docs_dir: str, persist_dir: str):
    """构建知识库向量存储"""
    print(f"正在加载文档：{docs_dir}")
    loader = DirectoryLoader(docs_dir, glob="**/*.txt", loader_cls=TextLoader, loader_kwargs={'encoding': 'utf-8'})
    documents = loader.load()
    print(f"加载了 {len(documents)} 个文档")

    # 文本分割
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]
    )
    chunks = text_splitter.split_documents(documents)
    print(f"分割为 {len(chunks)} 个片段")

    # 初始化嵌入模型（使用 Ollama bge-m3）
    embeddings = OllamaEmbeddings(
        model="bge-m3",                     
        base_url="http://localhost:11434"   
    )

    # 创建并持久化向量库
    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_dir
    )
    vectordb.persist()
    print(f"向量库已保存至：{persist_dir}\n")

if __name__ == "__main__":
    # 构建售前知识库
    build_knowledge_base(
        docs_dir="./knowledge/presales",
        persist_dir="./chroma_db/presales"
    )
    # 构建售后知识库
    build_knowledge_base(
        docs_dir="./knowledge/aftersales",
        persist_dir="./chroma_db/aftersales"
    )
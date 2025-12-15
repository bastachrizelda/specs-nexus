import os
import pickle
import numpy as np
import faiss
import logging
from sentence_transformers import SentenceTransformer


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def build_index(data_path: str, index_path: str, mapping_path: str, delimiter: str = "\n\n") -> None:
    """
    Builds a FAISS index from the document chunks in the provided file and saves the index and mapping.

    Args:
        data_path (str): Path to the system information text file.
        index_path (str): Path to save the FAISS index (pickle file).
        mapping_path (str): Path to save the document mapping (pickle file).
        delimiter (str): Delimiter used to split the text file into chunks.
    """
    try:

        logging.info(f"Loading data from {data_path}...")
        with open(data_path, "r", encoding="utf-8") as f:
            data = f.read()


        documents = [chunk.strip() for chunk in data.split(delimiter) if chunk.strip()]
        if not documents:
            raise ValueError("No document chunks found. Check the dataset file formatting.")

        logging.info(f"Found {len(documents)} document chunks.")


        logging.info("Generating embeddings...")
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        embeddings = embedding_model.encode(documents)

        # Convert embeddings to a NumPy array of type float32
        embeddings_np = np.array(embeddings).astype("float32")


        logging.info("Building the FAISS index...")
        index = faiss.IndexFlatL2(embeddings_np.shape[1])
        index.add(embeddings_np)

        logging.info(f"Saving FAISS index to {index_path}...")
        with open(index_path, "wb") as f:
            pickle.dump(index, f)

        logging.info(f"Saving document mapping to {mapping_path}...")
        with open(mapping_path, "wb") as f:
            pickle.dump(documents, f)

        logging.info("System index built and saved successfully!")
    except Exception as e:
        logging.error("An error occurred while building the system index:")
        logging.error(e)

def main():
    data_file = "system_info.txt"
    index_file = "faiss_system_index.pkl"
    mapping_file = "system_doc_mapping.pkl"

    build_index(data_file, index_file, mapping_file)

if __name__ == "__main__":
    main()

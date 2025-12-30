
## Epic Description

Deliver a usable "chat with our documents" MVP over a limited corpus using Chroma and a simple RAG chain, including ingestion, indexing, API, and a minimal UI + evaluation set.

**Target Date:** By end of Week 8

---

## Features

### 1. Ingestion Pipeline v1 (Parse + Heuristic Chunking)

**Description:**  
Build a batch ingestion job to parse pilot documents (PDF/DOCX/MD) into text and chunk them with a simple heuristic strategy.

**Acceptance Criteria:**

- Supported formats defined and successfully parsed for pilot corpus
- Text normalized (remove boilerplate where feasible) and stored with doc metadata
- Heuristic chunking produces chunks (e.g., 300–500 tokens) with doc_id + source refs
- Failures logged without aborting the full batch
- Pipeline is idempotent (re-run does not duplicate records)

|Attribute|Value|
|---|---|
|**Estimated Effort**|6 dev-days|
|**Confidence**|High|
|**Dependencies**|E1 complete; pilot documents available and approved for use|
|**Priority**|High|

---

### 2. Chroma Setup & Vector Indexing

**Description:**  
Deploy/initialize Chroma and index document chunks with embeddings and retrieval-friendly metadata.

**Acceptance Criteria:**

- Chroma runs with persistence; collection schema defined
- Embeddings generated for all chunks using selected embedding model
- Metadata stored: doc_id, source path/URI, section/page (if available), timestamps, ACL placeholders
- Smoke test: top-k retrieval returns relevant chunks for sample questions
- Re-indexing supported without duplicating entries

|Attribute|Value|
|---|---|
|**Estimated Effort**|5 dev-days|
|**Confidence**|High|
|**Dependencies**|Ingestion pipeline v1; embeddings working|
|**Priority**|High|

---

### 3. Simple RAG Chain + REST API

**Description:**  
Implement a baseline LangChain RAG chain (Chroma retriever → prompt → LLM generation) and expose a REST endpoint.

**Acceptance Criteria:**

- Endpoint `POST /rag/query` accepts question (+ optional user context)
- Retrieves top-k chunks and generates an answer grounded in retrieved context
- Response returns: answer, cited sources (doc_id + snippet/offset), and retrieval metadata
- Prompt includes grounding instruction ("use only provided context or say you don't know")
- Integration tests pass on a representative set of pilot queries

|Attribute|Value|
|---|---|
|**Estimated Effort**|7 dev-days|
|**Confidence**|Medium|
|**Dependencies**|Chroma indexing; LLM baseline; auth/config baseline|
|**Priority**|High|

---

### 4. Minimal UI + Evaluation Set

**Description:**  
Provide a minimal UI (or lightweight client) for stakeholders and define a small evaluation set to validate usefulness and faithfulness.

**Acceptance Criteria:**

- Minimal UI (or internal client) supports Q&A and displays citations
- 20–30 test questions created for pilot corpus with expected source docs
- Manual evaluation run produces a short report: top failure modes + priority fixes
- Basic feedback mechanism captured (e.g., thumbs up/down + comment)
- Release notes document known limitations of MVP

|Attribute|Value|
|---|---|
|**Estimated Effort**|4 dev-days|
|**Confidence**|Medium|
|**Dependencies**|REST API available; pilot users identified|
|**Priority**|Medium|

---

## Summary Table

|Feature|Effort|Confidence|Priority|Dependencies|
|---|---|---|---|---|
|Ingestion Pipeline v1|6 dev-days|High|High|E1 complete; pilot documents available|
|Chroma Setup & Vector Indexing|5 dev-days|High|High|Ingestion pipeline v1; embeddings working|
|Simple RAG Chain + REST API|7 dev-days|Medium|High|Chroma indexing; LLM baseline; auth/config|
|Minimal UI + Evaluation Set|4 dev-days|Medium|Medium|REST API available; pilot users identified|

**Total Estimated Effort:** 22 dev-days
"""
ingest_policies.py — one-time RAG ingestion script
====================================================
Creates the dispute_policies pgvector table and populates it with
curated chargeback regulation clauses from Visa, Mastercard, PSD2,
and Dinacard. Run once before the demo or after a DB reset.

Usage:
    cd backend/files
    python ingest_policies.py

Requires:
    - DATABASE_URL in .env
    - pgvector extension enabled on Supabase (it is by default)
    - sentence-transformers installed (pip install sentence-transformers)
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

# ── Regulation clauses corpus ────────────────────────────────────────────────
# Each clause: source, clause_id, content.
# Content is written as plain prose so embeddings capture meaning, not legalese.

CLAUSES = [
    # ── Visa Dispute Resolution (VDR) ───────────────────────────────────────
    {
        "source":    "Visa Dispute Resolution",
        "clause_id": "VDR-11.1.3",
        "content": (
            "Duplicate transaction dispute: A cardholder may dispute a transaction "
            "if the same purchase was charged twice to their card at the same merchant "
            "on the same day with the same amount. A valid duplicate must show two "
            "separate approval codes and the transactions must have occurred within "
            "30 minutes of each other. The second charge should be reversed."
        ),
    },
    {
        "source":    "Visa Dispute Resolution",
        "clause_id": "VDR-11.1.4",
        "content": (
            "Processing error — incorrect amount: A cardholder can dispute a transaction "
            "where the amount charged differs from the amount authorised at the point of sale. "
            "Evidence required: original receipt showing authorised amount and the transaction "
            "record showing the charged amount."
        ),
    },
    {
        "source":    "Visa Dispute Resolution",
        "clause_id": "VDR-10.4.1",
        "content": (
            "Unauthorised transaction: If a cardholder did not authorise a transaction, "
            "the issuer may raise a chargeback. The card must not have been present and "
            "the cardholder must have reported the card lost or stolen prior to the transaction, "
            "or the transaction must show clear signs of fraud."
        ),
    },
    {
        "source":    "Visa Dispute Resolution",
        "clause_id": "VDR-11.4",
        "content": (
            "Filing time limit: A dispute must be filed within 120 days of the transaction "
            "processing date or the date the cardholder first became aware of the charge, "
            "whichever is later. Disputes filed after this period are not eligible for chargeback."
        ),
    },
    {
        "source":    "Visa Dispute Resolution",
        "clause_id": "VDR-11.2",
        "content": (
            "Reversal remedy for confirmed duplicate: When a duplicate transaction is confirmed, "
            "the remedy is a full reversal of the second (duplicate) transaction. "
            "The original transaction stands. The merchant receives a chargeback for the "
            "duplicate amount and must accept the reversal without representment if the "
            "evidence clearly shows two charges for the same purchase."
        ),
    },
    # ── Mastercard Chargeback Guide ──────────────────────────────────────────
    {
        "source":    "Mastercard Chargeback Guide",
        "clause_id": "MC-4853",
        "content": (
            "Reason code 4853 — Cardholder dispute: Duplicate processing. "
            "The cardholder was charged more than once for the same goods or services. "
            "The two transactions must involve the same card, the same merchant, "
            "the same amount, and must have been processed within 24 hours. "
            "Both must carry distinct transaction identifiers."
        ),
    },
    {
        "source":    "Mastercard Chargeback Guide",
        "clause_id": "MC-4853-R",
        "content": (
            "Remedy for reason code 4853 duplicate processing: The second transaction "
            "must be reversed for the full amount. If the merchant can demonstrate that "
            "two separate purchases occurred (different items, different receipts), "
            "the chargeback may be rejected via representment with supporting evidence."
        ),
    },
    {
        "source":    "Mastercard Chargeback Guide",
        "clause_id": "MC-4837",
        "content": (
            "Reason code 4837 — No cardholder authorization: Used when a transaction "
            "appears on the cardholder's statement that they did not authorize. "
            "Distinct from duplicate processing: the cardholder denies ever making "
            "the purchase, as opposed to denying only the second of two charges. "
            "Requires a cardholder affidavit and investigation of card-present evidence."
        ),
    },
    {
        "source":    "Mastercard Chargeback Guide",
        "clause_id": "MC-4853-TL",
        "content": (
            "Time limit for reason code 4853: Chargeback must be filed within 120 days "
            "of the transaction date. For recurring transactions, the 120-day period "
            "starts from the date the cardholder first noticed the duplicate charge "
            "on their statement."
        ),
    },
    # ── PSD2 Directive ───────────────────────────────────────────────────────
    {
        "source":    "PSD2 Directive",
        "clause_id": "PSD2-Art73",
        "content": (
            "Article 73 — Refund for unauthorised payment transactions: "
            "The payment service provider (PSP) is liable for an unauthorised payment "
            "transaction and must refund the payer the full amount of the unauthorised "
            "transaction immediately, and in any event no later than the end of the "
            "following business day after becoming aware of the transaction."
        ),
    },
    {
        "source":    "PSD2 Directive",
        "clause_id": "PSD2-Art74",
        "content": (
            "Article 74 — Payer's liability for unauthorised transactions: "
            "The payer bears the losses up to a maximum of EUR 50 for unauthorised "
            "transactions arising from the use of a lost or stolen payment instrument "
            "or from the misappropriation of a payment instrument. "
            "This cap does not apply if the payer acted with gross negligence or fraud."
        ),
    },
    {
        "source":    "PSD2 Directive",
        "clause_id": "PSD2-Art80",
        "content": (
            "Article 80 — Out-of-court complaint and redress: "
            "Payment service providers must respond to complaints within 15 business days. "
            "In exceptional circumstances, a holding reply must be sent within 15 business days "
            "and the final response provided within 35 business days."
        ),
    },
    # ── Dinacard Operating Rules ─────────────────────────────────────────────
    {
        "source":    "Dinacard Operating Rules",
        "clause_id": "DC-6.2.1",
        "content": (
            "Duplicate transaction definition: A transaction is considered a duplicate "
            "if the same PAN was charged the same amount at the same terminal within "
            "60 minutes of a prior approved transaction, and the cardholder did not "
            "initiate a second purchase. Both transactions must carry different approval codes."
        ),
    },
    {
        "source":    "Dinacard Operating Rules",
        "clause_id": "DC-7.1",
        "content": (
            "Member bank obligations for dispute resolution: The acquiring bank must "
            "investigate all cardholder dispute claims within 30 calendar days. "
            "If a duplicate transaction is confirmed, the acquiring bank must initiate "
            "a reversal within 5 business days and notify the issuing bank."
        ),
    },
    {
        "source":    "Dinacard Operating Rules",
        "clause_id": "DC-8.4",
        "content": (
            "Chargeback time limit: Disputes must be submitted within 60 days of the "
            "transaction date. After 60 days, the card scheme will not process the "
            "chargeback and the cardholder's only recourse is a civil claim against "
            "the merchant."
        ),
    },
]


# ── DB setup and ingestion ───────────────────────────────────────────────────

def setup_and_ingest():
    import psycopg2
    from sentence_transformers import SentenceTransformer

    print("Loading embedding model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print(f"Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print("Enabling pgvector extension...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    print("Creating dispute_policies table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dispute_policies (
            id         SERIAL PRIMARY KEY,
            source     VARCHAR(100) NOT NULL,
            clause_id  VARCHAR(50)  NOT NULL UNIQUE,
            content    TEXT         NOT NULL,
            embedding  vector(384)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_dispute_policies_embedding
        ON dispute_policies USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 10);
    """)
    conn.commit()

    print(f"Embedding and inserting {len(CLAUSES)} clauses...")
    for clause in CLAUSES:
        vec = model.encode(clause["content"], normalize_embeddings=True).tolist()
        vec_literal = "[" + ",".join(f"{x:.8f}" for x in vec) + "]"
        cur.execute(
            """
            INSERT INTO dispute_policies (source, clause_id, content, embedding)
            VALUES (%s, %s, %s, %s::vector)
            ON CONFLICT (clause_id) DO UPDATE
                SET content   = EXCLUDED.content,
                    embedding = EXCLUDED.embedding;
            """,
            (clause["source"], clause["clause_id"], clause["content"], vec_literal),
        )
        print(f"  ✓ {clause['source']} — {clause['clause_id']}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"\nDone. {len(CLAUSES)} clauses stored in dispute_policies.")


if __name__ == "__main__":
    setup_and_ingest()

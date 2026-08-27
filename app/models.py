import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Cantidad de pasos del wizard de onboarding (ver Candidate.onboarding_step
# más abajo) -- única fuente del número, para no duplicarlo entre
# api/account.py y api/profile.py. Subió a 5 al agregar el paso de
# directrices/declaraciones antes de la carga del CV -- los candidatos que
# ya tenían onboarding_finished=true con la numeración vieja (tope en 4)
# no se ven afectados, ese flag es independiente y nunca se recalcula.
TOTAL_ONBOARDING_STEPS = 5


def _uuid_pk():
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _bigserial_pk():
    return mapped_column(BigInteger, primary_key=True, autoincrement=True)


class Profile(Base):
    __tablename__ = "profiles"

    # Sin FK a auth.users a propósito — ver nota en db/0001_init.sql.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="candidate"
    )
    full_name: Mapped[str | None] = mapped_column(Text)
    # Viene de user_metadata.avatar_url (o .picture) del provider OAuth --
    # ver AuthUser en core/auth.py. Nunca lo pisamos con signup por
    # email/password, que no manda ninguno de los dos.
    avatar_url: Mapped[str | None] = mapped_column(Text)
    # "google", "linkedin_oidc" o "email" -- Supabase ya lo trackea solo en
    # auth.users.raw_app_meta_data.provider, esto es la copia de una sola
    # vez al crear la cuenta para poder segmentar/reportar desde acá sin
    # tocar el schema de auth.
    signup_provider: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text, nullable=False, server_default="es")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("role in ('candidate','recruiter','admin')", name="profiles_role_check"),
        CheckConstraint("locale in ('es','en')", name="profiles_locale_check"),
        {"schema": "public"},
    )


class Candidate(Base):
    __tablename__ = "candidates"

    # bigserial a propósito: id interno para joins/FKs, nunca se expone al
    # front. `token` es el identificador opaco y estable para exponer en
    # APIs (no muta si el candidato cambia el slug). OJO: no confundir con
    # `storage_token` acá abajo -- ese es otro campo, tiene que quedar
    # 100% privado y server-side (solo para armar paths de R2), nunca se
    # expone. Nombres parecidos, seguridad opuesta. Ver regla de
    # plataforma en 03-documento-tecnico.md §1.
    id: Mapped[int] = _bigserial_pk()
    token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    storage_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, server_default=text("gen_random_uuid()")
    )

    headline: Mapped[str | None] = mapped_column(Text)
    degree: Mapped[str | None] = mapped_column(Text)
    overview: Mapped[str | None] = mapped_column(Text)
    years_experience: Mapped[float | None] = mapped_column(Numeric(4, 1))
    years_experience_updated_at: Mapped[date | None] = mapped_column(Date)
    skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    interests: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )

    work_mode: Mapped[str | None] = mapped_column(Text)
    location_city: Mapped[str | None] = mapped_column(Text)
    location_country: Mapped[str | None] = mapped_column(Text)
    willing_relocate: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    salary_min: Mapped[float | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[float | None] = mapped_column(Numeric(12, 2))
    salary_currency: Mapped[str | None] = mapped_column(Text, server_default="MXN")

    linkedin_url: Mapped[str | None] = mapped_column(Text)
    github_url: Mapped[str | None] = mapped_column(Text)
    portfolio_url: Mapped[str | None] = mapped_column(Text)
    youtube_url: Mapped[str | None] = mapped_column(Text)

    detected_language: Mapped[str | None] = mapped_column(Text)
    is_risky_prompt: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    contact_email: Mapped[str | None] = mapped_column(Text)
    contact_phone: Mapped[str | None] = mapped_column(Text)
    share_email: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    share_phone: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    agent_language: Mapped[str] = mapped_column(Text, nullable=False, server_default="es")
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_searchable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Paso más avanzado del wizard de onboarding que este candidato alcanzó
    # (1=directrices/declaraciones, 2=CV, 3=datos, 4=preguntas,
    # 5=compartir/listo) -- permite retomar en el siguiente login en vez de
    # reempezar desde cero si lo abandonó.
    onboarding_step: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    # Marca explícita e independiente del número de pasos -- si el wizard
    # gana un paso más en el futuro, "onboarding_step" solo no alcanza para
    # saber quién ya había terminado con la versión vieja vs. quién quedó a
    # medias con la nueva. Se setea una sola vez (ver update_profile en
    # api/profile.py), nunca se vuelve a false.
    onboarding_finished: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    onboarding_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Los dos checkboxes del paso 1 del wizard (ver onboarding/page.tsx,
    # guidelines.ackQuality/ackResponsibility) -- se guardan como evidencia
    # de que el candidato autorizó el uso de su CV bajo esas condiciones
    # antes de subirlo. cv_ack_at lo setea el servidor, no el cliente, para
    # que la marca de tiempo sirva como prueba.
    cv_quality_ack: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    cv_responsibility_ack: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    cv_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile_embedding: Mapped[list[float] | None] = mapped_column(Vector(512))

    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    cv_documents: Mapped[list["CVDocument"]] = relationship(
        "CVDocument", back_populates="candidate"
    )
    embeddings: Mapped[list["CandidateEmbedding"]] = relationship(
        "CandidateEmbedding", back_populates="candidate"
    )

    __table_args__ = (
        CheckConstraint("work_mode in ('remote','hybrid','onsite')", name="candidates_work_mode_check"),
        CheckConstraint("agent_language in ('es','en')", name="candidates_agent_language_check"),
        CheckConstraint("status in ('draft','processing','ready','error')", name="candidates_status_check"),
        CheckConstraint("detected_language in ('es','en','other')", name="candidates_detected_language_check"),
        Index("candidates_slug_idx", "slug"),
        Index(
            "candidates_is_searchable_work_mode_location_country_idx",
            "is_searchable", "work_mode", "location_country",
        ),
        Index("candidates_skills_idx", "skills", postgresql_using="gin"),
        Index(
            "candidates_profile_embedding_idx",
            "profile_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"profile_embedding": "vector_cosine_ops"},
        ),
        {"schema": "public"},
    )


class CVDocument(Base):
    __tablename__ = "cv_documents"

    id: Mapped[int] = _bigserial_pk()
    token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, server_default=text("gen_random_uuid()")
    )
    candidate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("public.candidates.id", ondelete="CASCADE"), nullable=False
    )
    r2_key: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    extracted: Mapped[dict | None] = mapped_column(JSONB)
    # Denormalizado acá (aparte de vivir también dentro de `extracted`) para
    # no tener que parsear el JSON completo solo para listar sugerencias por
    # CV -- este documento es el dueño natural del dato, no el candidato
    # (que puede tener varios CVs a lo largo del tiempo).
    suggestions: Mapped[list | None] = mapped_column(JSONB, server_default=text("'[]'"))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="uploaded")
    error_message: Mapped[str | None] = mapped_column(Text)
    # Estado del chunking + embeddings por sección, que corre en background
    # después de responder /api/cv/process -- independiente de `status`
    # (que es el pipeline síncrono de parseo del PDF).
    chunks_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="cv_documents")

    __table_args__ = (
        CheckConstraint("status in ('uploaded','parsing','parsed','failed')", name="cv_documents_status_check"),
        CheckConstraint(
            "chunks_status in ('pending','done','failed')", name="cv_documents_chunks_status_check"
        ),
        Index("cv_documents_candidate_id_is_current_idx", "candidate_id", "is_current"),
        {"schema": "public"},
    )


class CVChunk(Base):
    __tablename__ = "cv_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("public.candidates.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("public.cv_documents.id", ondelete="CASCADE")
    )
    section: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'")
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512))
    token_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("cv_chunks_candidate_id_idx", "candidate_id"),
        Index("cv_chunks_section_idx", "section"),
        Index(
            "cv_chunks_embedding_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        {"schema": "public"},
    )


class QuickQuestion(Base):
    __tablename__ = "quick_questions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    candidate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("public.candidates.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("char_length(question) <= 150", name="quick_questions_question_check"),
        CheckConstraint("position between 1 and 5", name="quick_questions_position_check"),
        UniqueConstraint("candidate_id", "position"),
        {"schema": "public"},
    )


class CandidateTier(Base):
    __tablename__ = "candidate_tiers"

    candidate_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("public.candidates.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tier: Mapped[str] = mapped_column(Text, nullable=False, server_default="base")
    unlocked_by: Mapped[str | None] = mapped_column(Text)
    referral_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    share_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    donated_total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0")
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("tier in ('base','impulso','alcance')", name="candidate_tiers_tier_check"),
        CheckConstraint("unlocked_by in ('donation','share','referrals','manual')", name="candidate_tiers_unlocked_by_check"),
        {"schema": "public"},
    )


class Share(Base):
    __tablename__ = "shares"

    id: Mapped[uuid.UUID] = _uuid_pk()
    candidate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("public.candidates.id", ondelete="CASCADE"), nullable=False
    )
    ref_token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "channel in ('linkedin','x','whatsapp','facebook','instagram','reddit','copy','other')",
            name="shares_channel_check",
        ),
        Index("shares_ref_token_idx", "ref_token"),
        Index("shares_candidate_id_idx", "candidate_id"),
        {"schema": "public"},
    )


class ReferralVisit(Base):
    __tablename__ = "referral_visits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    share_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.shares.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("public.candidates.id", ondelete="CASCADE"), nullable=False
    )
    visitor_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    dwell_ms: Mapped[int | None] = mapped_column(Integer)
    visit_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("current_date")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        # Parcial: solo dedupea visitas VÁLIDAS. Si no fuera parcial, una
        # visita inválida temprano en el día (rebote < 10s) ocuparía la
        # clave y bloquearía -- vía el mismo IntegrityError que el código
        # trata como "ya contada" -- que una visita genuinamente válida
        # del mismo visitante más tarde ese día se llegue a registrar,
        # perdiendo el crédito de referido para siempre ese día.
        Index(
            "referral_visits_daily_unique",
            "candidate_id", "visitor_hash", "visit_date",
            unique=True,
            postgresql_where=text("is_valid"),
        ),
        Index("referral_visits_candidate_id_is_valid_idx", "candidate_id", "is_valid"),
        {"schema": "public"},
    )


class Contribution(Base):
    __tablename__ = "contributions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    candidate_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("public.candidates.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text, unique=True)
    amount: Mapped[float | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str | None] = mapped_column(Text, server_default="MXN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("provider in ('stripe','mercadopago')", name="contributions_provider_check"),
        {"schema": "public"},
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = _bigserial_pk()
    token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, server_default=text("gen_random_uuid()")
    )
    candidate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("public.candidates.id", ondelete="CASCADE"), nullable=False
    )
    visitor_hash: Mapped[str | None] = mapped_column(Text)
    langsmith_run: Mapped[str | None] = mapped_column(Text)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = {"schema": "public"}


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("public.conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_ids: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("role in ('user','assistant')", name="messages_role_check"),
        Index("messages_conversation_id_created_at_idx", "conversation_id", "created_at"),
        {"schema": "public"},
    )


class Recruiter(Base):
    __tablename__ = "recruiters"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    company: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default="free")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("plan in ('free','pro','team')", name="recruiters_plan_check"),
        {"schema": "public"},
    )


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[uuid.UUID] = _uuid_pk()
    recruiter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.recruiters.id", ondelete="CASCADE"), nullable=False
    )
    raw_query: Mapped[str] = mapped_column(Text, nullable=False)
    parsed: Mapped[dict | None] = mapped_column(JSONB)
    results: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = {"schema": "public"}


class ContactRequest(Base):
    __tablename__ = "contact_requests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    recruiter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.recruiters.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("public.candidates.id", ondelete="CASCADE"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # Snapshot denormalizado del email del reclutador al momento del
    # contacto, tomado del JWT (AuthUser.email) -- no hay columna de email
    # alcanzable por SQLAlchemy, auth.users de Supabase no está mapeado acá.
    recruiter_email: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # NULL = nunca abrió la conversación -- todo cuenta como no leído. Un
    # timestamp por lado alcanza para "conversación nueva" y "mensajes
    # nuevos" a la vez (ver migración a4f2e9c17b83).
    candidate_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recruiter_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status in ('pending','accepted','declined','revoked')", name="contact_requests_status_check"),
        UniqueConstraint("recruiter_id", "candidate_id"),
        {"schema": "public"},
    )


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    contact_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.contact_requests.id", ondelete="CASCADE"), nullable=False
    )
    sender_role: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("sender_role in ('candidate','recruiter')", name="contact_messages_sender_role_check"),
        Index("contact_messages_contact_request_id_idx", "contact_request_id"),
        {"schema": "public"},
    )


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.profiles.id", ondelete="CASCADE"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("push_subscriptions_user_id_idx", "user_id"),
        {"schema": "public"},
    )


class CandidateEmbedding(Base):
    __tablename__ = "candidate_embeddings"

    id: Mapped[int] = _bigserial_pk()
    candidate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("public.candidates.id", ondelete="CASCADE"), nullable=False
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="embeddings")

    __table_args__ = (
        Index(
            "candidate_embeddings_embedding_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("candidate_embeddings_candidate_id_idx", "candidate_id"),
        {"schema": "public"},
    )


class FeedbackReport(Base):
    # Beta abierta (RF-11): botón "reportar un error/mejora" siempre visible.
    # Sin FK a auth.users a propósito, igual que Profile -- puede venir de
    # un visitante sin cuenta.
    __tablename__ = "feedback_reports"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    email: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    loom_url: Mapped[str | None] = mapped_column(Text)
    page_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "user_id is not null or email is not null", name="feedback_reports_identity_check"
        ),
        {"schema": "public"},
    )


class RecruiterWaitlistSignup(Base):
    # RF pendiente: la búsqueda de candidatos para reclutadores todavía no
    # está lista -- esto es la lista de espera que reemplaza el signup real
    # mientras tanto (ver Header/landing/ContactModal, todos apuntan acá en
    # vez de a /login?role=recruiter).
    __tablename__ = "recruiter_waitlist_signups"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("email", name="recruiter_waitlist_signups_email_key"),
        {"schema": "public"},
    )

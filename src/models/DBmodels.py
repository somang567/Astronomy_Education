# models.py
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy.dialects.mysql import BINARY, DATETIME as MySQL_DATETIME
from sqlalchemy import Computed, text
from . import db  # Flask SQLAlchemy 인스턴스

# ------------------
# UUID helpers
# ------------------
def gen_uuid_bytes() -> bytes:
    return uuid.uuid4().bytes

def uuid_bytes_to_hex(b: bytes | None) -> str | None:
    if b is None:
        return None
    return uuid.UUID(bytes=b).hex

# ------------------
# Master tables
# ------------------
class Instrument(db.Model):
    __tablename__ = "instrument"
    instrument_id = db.Column(db.BigInteger, primary_key=True)
    name          = db.Column(db.String(191), nullable=False, unique=True)
    observatory   = db.Column(db.String(191))

    def __repr__(self):
        return f"<Instrument {self.instrument_id} {self.name!r}>"

class FileStorage(db.Model):
    __tablename__ = "file_storage"
    file_id     = db.Column(BINARY(16), primary_key=True, default=gen_uuid_bytes)
    file_path   = db.Column(db.String(512), nullable=False, unique=True)
    media_type  = db.Column(db.String(64))
    file_size   = db.Column(db.BigInteger)
    sha256_hash = db.Column(db.String(64), index=True)
    created_at  = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    def __repr__(self):
        return f"<FileStorage {uuid_bytes_to_hex(self.file_id)} path={self.file_path!r}>"

class Tag(db.Model):
    __tablename__ = "tag"
    tag_id = db.Column(db.BigInteger, primary_key=True)
    name   = db.Column(db.String(191), nullable=False, unique=True)

    def __repr__(self):
        return f"<Tag {self.tag_id} {self.name!r}>"

# ------------------
# FITS core
# ------------------
class FitsFile(db.Model):
    __tablename__ = "fits_file"
    fits_id           = db.Column(BINARY(16), primary_key=True, default=gen_uuid_bytes)
    storage_file_id   = db.Column(BINARY(16), db.ForeignKey("file_storage.file_id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    canonical_name    = db.Column(db.String(255), nullable=False)
    observed_at       = db.Column(MySQL_DATETIME(fsp=6), nullable=False)
    # Generated columns (이미 DB에 존재). 선언해 두면 ORM에서 읽기 전용으로 쓸 수 있음.
    observed_date     = db.Column(db.Date, Computed("DATE(observed_at)"), nullable=True)
    observed_hour     = db.Column(db.SmallInteger, Computed("HOUR(observed_at)"), nullable=True)
    instrument_id     = db.Column(db.BigInteger, db.ForeignKey("instrument.instrument_id"))
    status            = db.Column(db.Enum("NEW","PROCESSING","READY","FAILED"), nullable=False, server_default="READY")
    created_at        = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at        = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"), onupdate=datetime.utcnow)

    # Relations
    storage    = db.relationship("FileStorage", lazy="joined")
    instrument = db.relationship("Instrument", lazy="joined")
    hdus       = db.relationship("FitsHDU", back_populates="fits", cascade="all, delete-orphan", passive_deletes=True)
    previews   = db.relationship("PreviewImage", back_populates="fits", cascade="all, delete-orphan", passive_deletes=True)
    slits      = db.relationship("SlitBoundary", back_populates="fits", cascade="all, delete-orphan", passive_deletes=True)
    tags       = db.relationship("Tag", secondary="fits_tag_map", lazy="selectin")

    # Convenience (이전 코드 호환)
    @property
    def filename(self) -> str:
        return self.original_filename or self.canonical_name

    @property
    def fits_id_hex(self) -> str:
        return uuid_bytes_to_hex(self.fits_id)

    def __repr__(self):
        return f"<FitsFile {self.fits_id_hex} {self.filename!r}>"

class FitsHDU(db.Model):
    __tablename__ = "fits_hdu"
    hdu_id      = db.Column(BINARY(16), primary_key=True, default=gen_uuid_bytes)
    fits_id     = db.Column(BINARY(16), db.ForeignKey("fits_file.fits_id", ondelete="CASCADE"), nullable=False, index=True)
    hdu_index   = db.Column(db.Integer, nullable=False)
    hdu_type    = db.Column(db.Enum("IMAGE","TABLE","OTHER"), nullable=False, server_default="IMAGE")
    bitpix      = db.Column(db.SmallInteger)
    shape_json  = db.Column(db.JSON)
    header_json = db.Column(db.JSON)
    created_at  = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    fits = db.relationship("FitsFile", back_populates="hdus", lazy="joined")

    __table_args__ = (
        db.UniqueConstraint("fits_id", "hdu_index", name="uq_fits_hdu"),
    )

class FitsHeaderKeyvalue(db.Model):
    __tablename__ = "fits_header_keyvalue"
    keyvalue_id = db.Column(db.BigInteger, primary_key=True)
    fits_id     = db.Column(BINARY(16), db.ForeignKey("fits_file.fits_id", ondelete="CASCADE"), nullable=False, index=True)
    header_key  = db.Column(db.String(64), nullable=False)
    value_text  = db.Column(db.String(255))
    value_num   = db.Column(db.Float)
    value_time  = db.Column(MySQL_DATETIME(fsp=6))

    __table_args__ = (
        db.UniqueConstraint("fits_id", "header_key", name="uq_fits_key"),
        db.Index("idx_header_key", "header_key"),
        db.Index("idx_value_num", "value_num"),
    )

# ------------------
# Preview images
# ------------------
class PreviewImage(db.Model):
    __tablename__ = "preview_image"
    preview_id      = db.Column(BINARY(16), primary_key=True, default=gen_uuid_bytes)
    fits_id         = db.Column(BINARY(16), db.ForeignKey("fits_file.fits_id", ondelete="CASCADE"), nullable=False, index=True)
    hdu_id          = db.Column(BINARY(16), db.ForeignKey("fits_hdu.hdu_id", ondelete="SET NULL"))
    storage_file_id = db.Column(BINARY(16), db.ForeignKey("file_storage.file_id"), nullable=False, unique=True)
    image_kind      = db.Column(db.Enum("PREVIEW","THUMB","FRAME"), nullable=False, server_default="PREVIEW")
    frame_index     = db.Column(db.Integer)
    channel_name    = db.Column(db.String(32))
    width_px        = db.Column(db.Integer)
    height_px       = db.Column(db.Integer)
    stats_json      = db.Column(db.JSON)
    created_at      = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    fits    = db.relationship("FitsFile", back_populates="previews", lazy="joined")
    hdu     = db.relationship("FitsHDU", lazy="joined")
    storage = db.relationship("FileStorage", lazy="joined")

    __table_args__ = (
        db.UniqueConstraint("fits_id", "image_kind", "frame_index", "channel_name", name="uq_preview_per_fits"),
        db.Index("idx_image_kind", "image_kind"),
        db.Index("idx_frame_index", "frame_index"),
        db.Index("idx_channel_name", "channel_name"),
    )

# ------------------
# Slit / Spectrum
# ------------------
class SlitBoundary(db.Model):
    __tablename__ = "slit_boundary"
    slit_id      = db.Column(BINARY(16), primary_key=True, default=gen_uuid_bytes)
    fits_id      = db.Column(BINARY(16), db.ForeignKey("fits_file.fits_id", ondelete="CASCADE"), nullable=False, index=True)
    label        = db.Column(db.String(191))
    geometry_json = db.Column(db.JSON)        # {x,y,width,height} or polygon
    default_params_json = db.Column(db.JSON)
    created_at   = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at   = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"), onupdate=datetime.utcnow)

    fits     = db.relationship("FitsFile", back_populates="slits", lazy="joined")
    requests = db.relationship("SpectrumRequest", back_populates="slit", cascade="all, delete-orphan", passive_deletes=True)

class SpectrumRequest(db.Model):
    __tablename__ = "spectrum_request"
    request_id  = db.Column(BINARY(16), primary_key=True, default=gen_uuid_bytes)
    slit_id     = db.Column(BINARY(16), db.ForeignKey("slit_boundary.slit_id", ondelete="CASCADE"), nullable=False, index=True)
    point_x     = db.Column(db.Integer)
    point_y     = db.Column(db.Integer)
    region_json = db.Column(db.JSON)
    params_hash = db.Column(db.String(64), nullable=False)   # dedup key
    params_json = db.Column(db.JSON)
    status      = db.Column(db.Enum("NEW","PROCESSING","READY","FAILED"), nullable=False, server_default="NEW")
    created_at  = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at  = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"), onupdate=datetime.utcnow)

    slit    = db.relationship("SlitBoundary", back_populates="requests", lazy="joined")
    results = db.relationship("SpectrumResult", back_populates="request", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        db.UniqueConstraint("slit_id", "point_x", "point_y", "params_hash", name="uq_dedup_request"),
        db.Index("idx_request_status", "status"),
    )

class SpectrumResult(db.Model):
    __tablename__ = "spectrum_result"
    result_id    = db.Column(BINARY(16), primary_key=True, default=gen_uuid_bytes)
    request_id   = db.Column(BINARY(16), db.ForeignKey("spectrum_request.request_id", ondelete="CASCADE"), nullable=False, index=True)
    data_file_id = db.Column(BINARY(16), db.ForeignKey("file_storage.file_id"), nullable=False)
    preview_id   = db.Column(BINARY(16), db.ForeignKey("preview_image.preview_id", ondelete="SET NULL"))
    sample_count = db.Column(db.Integer)
    created_at   = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    request = db.relationship("SpectrumRequest", back_populates="results", lazy="joined")
    data    = db.relationship("FileStorage", lazy="joined")
    preview = db.relationship("PreviewImage", lazy="joined")

# ------------------
# Jobs / Events
# ------------------
class JobTask(db.Model):
    __tablename__ = "job_task"
    task_id      = db.Column(BINARY(16), primary_key=True, default=gen_uuid_bytes)
    task_type    = db.Column(db.Enum("INGEST","PREVIEW","SPLIT","SPECTRUM","EXPORT"), nullable=False)
    fits_id      = db.Column(BINARY(16), db.ForeignKey("fits_file.fits_id", ondelete="SET NULL"))
    slit_id      = db.Column(BINARY(16), db.ForeignKey("slit_boundary.slit_id", ondelete="SET NULL"))
    request_id   = db.Column(BINARY(16), db.ForeignKey("spectrum_request.request_id", ondelete="SET NULL"))
    status       = db.Column(db.Enum("QUEUED","RUNNING","SUCCESS","FAILED"), nullable=False, server_default="QUEUED")
    progress_pct = db.Column(db.SmallInteger, nullable=False, server_default="0")
    message      = db.Column(db.String(512))
    created_at   = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at   = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"), onupdate=datetime.utcnow)

    fits    = db.relationship("FitsFile", lazy="joined")
    slit    = db.relationship("SlitBoundary", lazy="joined")
    request = db.relationship("SpectrumRequest", lazy="joined")
    events  = db.relationship("JobEvent", back_populates="task", cascade="all, delete-orphan", passive_deletes=True)

class JobEvent(db.Model):
    __tablename__ = "job_event"
    event_id     = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    task_id      = db.Column(BINARY(16), db.ForeignKey("job_task.task_id", ondelete="CASCADE"), nullable=False, index=True)
    level        = db.Column(db.Enum("INFO","WARN","ERROR"), nullable=False, server_default="INFO")
    progress_pct = db.Column(db.SmallInteger)
    message      = db.Column(db.String(512), nullable=False)
    created_at   = db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    task = db.relationship("JobTask", back_populates="events", lazy="joined")

# ------------------
# Tag mapping (M2M)
# ------------------
class FitsTagMap(db.Model):
    __tablename__ = "fits_tag_map"
    fits_id = db.Column(BINARY(16), db.ForeignKey("fits_file.fits_id", ondelete="CASCADE"), primary_key=True)
    tag_id  = db.Column(db.BigInteger, db.ForeignKey("tag.tag_id", ondelete="CASCADE"), primary_key=True)

# ------------------
# Singleton: current local upload
# ------------------
class CurrentLocalUpload(db.Model):
    __tablename__ = "current_local_upload"
    slot_id   = db.Column(db.SmallInteger, primary_key=True, default=1)
    fits_id   = db.Column(BINARY(16), db.ForeignKey("fits_file.fits_id", ondelete="SET NULL"))
    updated_at= db.Column(db.DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"), onupdate=datetime.utcnow)

    fits = db.relationship("FitsFile", lazy="joined")

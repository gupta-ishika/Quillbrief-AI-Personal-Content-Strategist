from sqlalchemy.orm import Session

from app.db.models import Creator


def get_creator(db: Session) -> Creator | None:
    return db.query(Creator).first()


def get_or_create_creator(db: Session, display_name: str = "Creator") -> Creator:
    creator = db.query(Creator).first()
    if not creator:
        creator = Creator(display_name=display_name)
        db.add(creator)
        db.commit()
        db.refresh(creator)
    return creator


def update_creator_channel(
    db: Session,
    channel_id: str | None,
    channel_handle: str | None,
    channel_title: str | None,
    verified: bool = False,
) -> Creator:
    creator = get_or_create_creator(db)
    creator.youtube_channel_id = channel_id
    creator.youtube_channel_handle = channel_handle
    creator.youtube_channel_title = channel_title
    creator.youtube_channel_verified = verified
    db.commit()
    db.refresh(creator)
    return creator


def clear_creator_channel(db: Session) -> Creator:
    creator = get_or_create_creator(db)
    creator.youtube_channel_id = None
    creator.youtube_channel_handle = None
    creator.youtube_channel_title = None
    creator.youtube_channel_verified = False
    db.commit()
    db.refresh(creator)
    return creator

import os
import hashlib
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User as UserSchema, Listing as ListingSchema, Message as MessageSchema, Saved as SavedSchema

app = FastAPI(title="FluxMarket API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utils
class ObjectIdStr(str):
    @classmethod
    def validate(cls, v: str) -> str:
        try:
            ObjectId(v)
            return v
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid id")

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Auth Endpoints
class RegisterBody(BaseModel):
    name: str
    email: str
    password: str
    location: Optional[str] = None

class LoginBody(BaseModel):
    email: str
    password: str

@app.post("/api/auth/register")
def register(body: RegisterBody):
    # check existing
    existing = db.user.find_one({"email": body.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = UserSchema(
        name=body.name,
        email=body.email,
        password_hash=sha256(body.password),
        location=body.location,
        avatar_url=None,
        is_active=True,
    )
    user_id = create_document("user", user)
    return {"id": user_id, "name": user.name, "email": user.email}

@app.post("/api/auth/login")
def login(body: LoginBody):
    user = db.user.find_one({"email": body.email})
    if not user or user.get("password_hash") != sha256(body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"id": str(user["_id"]), "name": user["name"], "email": user["email"]}


# Listings Endpoints
class CreateListingBody(BaseModel):
    user_id: str
    title: str
    description: str
    price: float
    category: str
    listing_type: str = "sale"
    location: Optional[str] = None
    images: Optional[List[str]] = []

@app.get("/api/listings")
def list_listings(q: Optional[str] = None, category: Optional[str] = None, limit: int = Query(20, ge=1, le=100)):
    filter_q = {"status": "active"}
    if category:
        filter_q["category"] = category
    if q:
        # Simple text search via regex
        filter_q["title"] = {"$regex": q, "$options": "i"}
    docs = db.listing.find(filter_q).limit(limit)
    listings = []
    for d in docs:
        d["id"] = str(d.pop("_id"))
        listings.append(d)
    return {"items": listings}

@app.post("/api/listings")
def create_listing(body: CreateListingBody):
    # ensure owner exists
    if not ObjectId.is_valid(body.user_id):
        raise HTTPException(status_code=400, detail="Invalid user id")
    owner = db.user.find_one({"_id": ObjectId(body.user_id)})
    if not owner:
        raise HTTPException(status_code=404, detail="User not found")

    listing = ListingSchema(
        user_id=body.user_id,
        title=body.title,
        description=body.description,
        price=body.price,
        category=body.category,
        listing_type=body.listing_type if body.listing_type in ["sale", "service", "rent"] else "sale",
        location=body.location,
        images=body.images or [],
        status="active",
    )
    listing_id = create_document("listing", listing)
    return {"id": listing_id}


# Saved Listings
class SaveBody(BaseModel):
    user_id: str
    listing_id: str

@app.post("/api/saved")
def save_listing(body: SaveBody):
    if not (ObjectId.is_valid(body.user_id) and ObjectId.is_valid(body.listing_id)):
        raise HTTPException(status_code=400, detail="Invalid ids")

    existing = db.saved.find_one({"user_id": body.user_id, "listing_id": body.listing_id})
    if existing:
        return {"status": "already_saved"}

    saved = SavedSchema(user_id=body.user_id, listing_id=body.listing_id)
    saved_id = create_document("saved", saved)
    return {"id": saved_id}

@app.get("/api/saved/{user_id}")
def get_saved(user_id: str):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id")
    docs = db.saved.find({"user_id": user_id})
    result = []
    for d in docs:
        d["id"] = str(d.pop("_id"))
        result.append(d)
    return {"items": result}


# Messaging
class SendMessageBody(BaseModel):
    listing_id: str
    from_user_id: str
    to_user_id: str
    content: str

@app.post("/api/messages")
def send_message(body: SendMessageBody):
    if not (ObjectId.is_valid(body.listing_id) and ObjectId.is_valid(body.from_user_id) and ObjectId.is_valid(body.to_user_id)):
        raise HTTPException(status_code=400, detail="Invalid ids")
    # ensure listing exists
    if not db.listing.find_one({"_id": ObjectId(body.listing_id)}):
        raise HTTPException(status_code=404, detail="Listing not found")

    msg = MessageSchema(
        listing_id=body.listing_id,
        from_user_id=body.from_user_id,
        to_user_id=body.to_user_id,
        content=body.content,
        read=False,
    )
    msg_id = create_document("message", msg)
    return {"id": msg_id}

@app.get("/api/messages/thread")
def get_thread(listing_id: str, a: str, b: str, limit: int = Query(50, ge=1, le=200)):
    # messages between user a and b about listing
    if not (ObjectId.is_valid(listing_id) and ObjectId.is_valid(a) and ObjectId.is_valid(b)):
        raise HTTPException(status_code=400, detail="Invalid ids")
    docs = db.message.find({
        "listing_id": listing_id,
        "$or": [
            {"from_user_id": a, "to_user_id": b},
            {"from_user_id": b, "to_user_id": a},
        ],
    }).sort("created_at", 1).limit(limit)
    out = []
    for d in docs:
        d["id"] = str(d.pop("_id"))
        out.append(d)
    return {"items": out}


@app.get("/")
def read_root():
    return {"message": "FluxMarket backend running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

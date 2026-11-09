from datetime import datetime, timedelta, timezone
from typing import Optional
import os, re, hashlib
import feedparser, httpx
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, String, Text, DateTime, Float, ForeignKey, Boolean, select, or_
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

DATABASE_URL=os.getenv("DATABASE_URL","sqlite:///./trustnews.db")
engine=create_engine(DATABASE_URL, connect_args={"check_same_thread":False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal=sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
SECRET=os.getenv("JWT_SECRET","local-dev-secret-change-me")
ALGORITHM="HS256"; pwd=CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth=OAuth2PasswordBearer(tokenUrl="/auth/login")

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__="users"
    id:Mapped[int]=mapped_column(primary_key=True)
    email:Mapped[str]=mapped_column(String(255),unique=True,index=True)
    name:Mapped[str]=mapped_column(String(120))
    password_hash:Mapped[str]=mapped_column(String(255))
    interests:Mapped[str]=mapped_column(Text,default="")
    created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Article(Base):
    __tablename__="articles"
    id:Mapped[int]=mapped_column(primary_key=True)
    title:Mapped[str]=mapped_column(Text)
    description:Mapped[str]=mapped_column(Text,default="")
    url:Mapped[str]=mapped_column(Text,unique=True,index=True)
    image_url:Mapped[str]=mapped_column(Text,default="")
    source:Mapped[str]=mapped_column(String(255),default="Unknown")
    category:Mapped[str]=mapped_column(String(120),default="General")
    published_at:Mapped[datetime]=mapped_column(DateTime,index=True)
    credibility:Mapped[float]=mapped_column(Float,default=.5)
    language:Mapped[str]=mapped_column(String(20),default="en")
class Interaction(Base):
    __tablename__="interactions"
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    article_id:Mapped[int]=mapped_column(ForeignKey("articles.id"),index=True)
    action:Mapped[str]=mapped_column(String(30))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Bookmark(Base):
    __tablename__="bookmarks"
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    article_id:Mapped[int]=mapped_column(ForeignKey("articles.id"),index=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))

Base.metadata.create_all(engine)
app=FastAPI(title="TrustNews API",version="1.0.0",description="Personalized, diverse news with transparent recommendation signals.")
app.add_middleware(CORSMiddleware,allow_origins=os.getenv("CORS_ORIGINS","http://localhost:5173").split(","),allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
def db():
    s=SessionLocal()
    try: yield s
    finally: s.close()
def hash_pw(p): return pwd.hash(p)
def verify(p,h): return pwd.verify(p,h)
def token(user):
    return jwt.encode({"sub":str(user.id),"exp":datetime.now(timezone.utc)+timedelta(days=7)},SECRET,algorithm=ALGORITHM)
def current_user(t:str=Depends(oauth),s:Session=Depends(db)):
    try: uid=int(jwt.decode(t,SECRET,algorithms=[ALGORITHM])["sub"])
    except (JWTError,ValueError): raise HTTPException(401,"Your session expired. Please sign in again.")
    u=s.get(User,uid)
    if not u: raise HTTPException(401,"Account not found")
    return u
class Register(BaseModel):
    name:str
    email:EmailStr
    password:str
class Preferences(BaseModel):
    interests:list[str]
class Feedback(BaseModel):
    action:str

@app.get("/health")
def health(): return {"status":"ok","service":"TrustNews API","time":datetime.now(timezone.utc).isoformat()}
@app.post("/auth/register")
def register(x:Register,s:Session=Depends(db)):
    if len(x.password)<8: raise HTTPException(400,"Password must contain at least 8 characters.")
    email=x.email.lower().strip()
    if s.scalar(select(User).where(User.email==email)): raise HTTPException(409,"An account with this email already exists.")
    u=User(name=x.name.strip(),email=email,password_hash=hash_pw(x.password))
    s.add(u); s.commit(); s.refresh(u)
    return {"access_token":token(u),"token_type":"bearer","user":user_json(u)}
@app.post("/auth/login")
def login(form:OAuth2PasswordRequestForm=Depends(),s:Session=Depends(db)):
    u=s.scalar(select(User).where(User.email==form.username.lower().strip()))
    if not u or not verify(form.password,u.password_hash): raise HTTPException(401,"Email or password is incorrect.")
    return {"access_token":token(u),"token_type":"bearer","user":user_json(u)}
def user_json(u): return {"id":u.id,"name":u.name,"email":u.email,"interests":split_interests(u.interests)}
def split_interests(s): return [x for x in (s or "").split("|") if x]
@app.get("/auth/me")
def me(u:User=Depends(current_user)): return user_json(u)
@app.put("/auth/preferences")
def prefs(x:Preferences,u:User=Depends(current_user),s:Session=Depends(db)):
    u.interests="|".join(dict.fromkeys([i.strip() for i in x.interests if i.strip()][:30])); s.commit(); return user_json(u)
def article_json(a,score=None,why=None):
    return {"id":a.id,"title":a.title,"description":a.description,"url":a.url,"image_url":a.image_url,"source":a.source,"category":a.category,"published_at":a.published_at.isoformat() if a.published_at else None,"credibility":a.credibility,"score":score,"reason":why}
@app.get("/articles")
def articles(category:Optional[str]=None,q:Optional[str]=None,limit:int=Query(40,ge=1,le=100),s:Session=Depends(db)):
    stmt=select(Article).order_by(Article.published_at.desc()).limit(limit)
    if category and category!="All": stmt=stmt.where(Article.category==category)
    if q: stmt=stmt.where(or_(Article.title.ilike(f"%{q}%"),Article.description.ilike(f"%{q}%"),Article.source.ilike(f"%{q}%")))
    return [article_json(a) for a in s.scalars(stmt).all()]
@app.get("/recommendations")
def recommendations(limit:int=Query(30,ge=1,le=100),u:User=Depends(current_user),s:Session=Depends(db)):
    arts=s.scalars(select(Article).order_by(Article.published_at.desc()).limit(500)).all()
    if not arts: return []
    interactions=s.scalars(select(Interaction).where(Interaction.user_id==u.id)).all()
    liked={i.article_id for i in interactions if i.action in ("like","read","open")}
    hidden={i.article_id for i in interactions if i.action in ("hide","dislike")}
    liked_articles=[s.get(Article,i) for i in liked]
    interests=set(split_interests(u.interests))
    def score(a):
        txt=(a.title+" "+a.description+" "+a.category).lower()
        interest=sum(2 for k in interests if k.lower() in txt)
        affinity=sum(1.5 for old in liked_articles if old and (old.category==a.category or old.source==a.source))
        age=max(0,(datetime.now(timezone.utc)-a.published_at.replace(tzinfo=timezone.utc) if a.published_at.tzinfo is None else datetime.now(timezone.utc)-a.published_at).total_seconds()/3600)
        fresh=max(0,1-age/72)
        popularity=0.05
        return .50*interest+.20*affinity+.15*fresh+.15*a.credibility+popularity
    ranked=sorted([a for a in arts if a.id not in hidden],key=score,reverse=True)
    # Greedy category/source diversification. Every item remains a real stored article.
    out=[]; cat_count={}; source_count={}
    while ranked and len(out)<limit:
        best=max(ranked,key=lambda a:score(a)-.22*cat_count.get(a.category,0)-.12*source_count.get(a.source,0))
        ranked.remove(best); out.append(best); cat_count[best.category]=cat_count.get(best.category,0)+1; source_count[best.source]=source_count.get(best.source,0)+1
    return [article_json(a,round(score(a),4),"Matched interests, reading signals, freshness, source metadata, and diversity balancing") for a in out]
@app.post("/articles/{article_id}/feedback")
def feedback(article_id:int,x:Feedback,u:User=Depends(current_user),s:Session=Depends(db)):
    if x.action not in {"open","read","like","dislike","hide"}: raise HTTPException(400,"Unsupported feedback action")
    if not s.get(Article,article_id): raise HTTPException(404,"Article not found")
    s.add(Interaction(user_id=u.id,article_id=article_id,action=x.action)); s.commit(); return {"ok":True}
@app.get("/bookmarks")
def bookmarks(u:User=Depends(current_user),s:Session=Depends(db)):
    ids=s.scalars(select(Bookmark.article_id).where(Bookmark.user_id==u.id)).all()
    return [article_json(s.get(Article,i)) for i in ids if s.get(Article,i)]
@app.post("/bookmarks/{article_id}")
def add_bookmark(article_id:int,u:User=Depends(current_user),s:Session=Depends(db)):
    if not s.get(Article,article_id): raise HTTPException(404,"Article not found")
    if not s.scalar(select(Bookmark).where(Bookmark.user_id==u.id,Bookmark.article_id==article_id)):
        s.add(Bookmark(user_id=u.id,article_id=article_id)); s.commit()
    return {"ok":True}
@app.delete("/bookmarks/{article_id}")
def remove_bookmark(article_id:int,u:User=Depends(current_user),s:Session=Depends(db)):
    b=s.scalar(select(Bookmark).where(Bookmark.user_id==u.id,Bookmark.article_id==article_id))
    if b: s.delete(b); s.commit()
    return {"ok":True}
@app.get("/stats")
def stats(s:Session=Depends(db),u:User=Depends(current_user)):
    arts=s.scalars(select(Article)).all()
    return {"article_count":len(arts),"publisher_count":len(set(a.source for a in arts)),"category_count":len(set(a.category for a in arts)),"interaction_count":s.scalar(select(Interaction.id).where(Interaction.user_id==u.id).count()) if False else len(s.scalars(select(Interaction).where(Interaction.user_id==u.id)).all())}
@app.post("/admin/ingest")
def ingest(u:User=Depends(current_user),s:Session=Depends(db)):
    # User token protects ingestion; configure NEWS_API_KEY on server. Feeds are explicit allowlist.
    key=os.getenv("NEWS_API_KEY","")
    if not key: raise HTTPException(503,"NEWS_API_KEY is not configured. Add it to .env and restart.")
    url=os.getenv("NEWS_API_URL","https://newsapi.org/v2")+"/everything"
    try:
        data=httpx.get(
    url,
    params={
        "q": "India",
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 100,
        "apiKey": key
    },
    timeout=20
).raise_for_status().json()
    except Exception as e: raise HTTPException(502,"News provider is temporarily unavailable.") from e
    added=0
    for item in data.get("articles",[]):
        link=item.get("url")
        title=item.get("title")
        if not link or not title or s.scalar(select(Article).where(Article.url==link)): continue
        src=item.get("source",{}).get("name") or "Unknown"
        pub=item.get("publishedAt")
        try: dt=datetime.fromisoformat(pub.replace("Z","+00:00"))
        except: dt=datetime.now(timezone.utc)
        desc=(item.get("description") or "")[:4000]
        category=guess_category(title+" "+desc)
        s.add(Article(title=title[:2000],description=desc,url=link,image_url=item.get("urlToImage") or "",source=src[:255],category=category,published_at=dt,credibility=.5))
        added+=1
    s.commit()
    return {"added":added,"provider":"NewsAPI","note":"Provider data is real; credibility is neutral until independently assessed."}
def guess_category(text):
    t=text.lower()
    for c,words in {"Technology":["tech","ai","software","cyber","mobile"],"Business":["market","business","stock","economy","company"],"Sports":["cricket","football","sport","match","player"],"Health":["health","medical","hospital","disease"],"Politics":["minister","government","election","parliament","politic"],"Science":["science","research","space","climate"]}.items():
        if any(w in t for w in words): return c
    return "General"

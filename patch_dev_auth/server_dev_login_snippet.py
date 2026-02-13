# Вставить в backend/server.py ПЕРЕД строкой:
#   @api_router.post("/auth/login", response_model=TokenResponse)

# ==================== DEV AUTH BYPASS ====================
DEV_AUTH_BYPASS = os.environ.get("DEV_AUTH_BYPASS", "").strip() == "1"

class DevLoginRequest(BaseModel):
    role: str  # "supplier" | "customer"
    email: Optional[str] = None
    phone: Optional[str] = None

@api_router.post("/dev/login", response_model=TokenResponse)
async def dev_login(data: DevLoginRequest):
    """DEV-only: login without password. Returns 404 when DEV_AUTH_BYPASS != 1."""
    if not DEV_AUTH_BYPASS:
        raise HTTPException(status_code=404, detail="Not Found")
    role = (data.role or "supplier").strip().lower()
    if role not in ("supplier", "customer"):
        raise HTTPException(status_code=400, detail="role must be supplier or customer")
    user = None
    company_id = None
    if data.email:
        user = await db.users.find_one({"email": data.email.strip(), "role": role}, {"_id": 0})
    if not user and data.phone:
        phone_norm = "".join(c for c in str(data.phone) if c.isdigit())[-10:]
        async for c in db.companies.find({"type": role}, {"_id": 0, "id": 1, "userId": 1, "phone": 1, "contactPersonPhone": 1}):
            cp = (c.get("phone") or c.get("contactPersonPhone") or "")
            if phone_norm in "".join(x for x in cp if x.isdigit()):
                user = await db.users.find_one({"id": c["userId"]}, {"_id": 0})
                company_id = c["id"]
                break
    if not user:
        user = await db.users.find_one({"role": role}, {"_id": 0})
    if user:
        if not company_id and user.get("role") != "responsible":
            company = await db.companies.find_one({"userId": user["id"]}, {"_id": 0, "id": 1})
            company_id = company["id"] if company else None
        token = create_access_token({"sub": user["id"], "role": user["role"]})
        return TokenResponse(
            access_token=token,
            user={"id": user["id"], "email": user.get("email", ""), "role": user["role"], "companyId": company_id}
        )
    user_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    email = data.email or f"dev-{role}@local.dev"
    now = datetime.now(timezone.utc).isoformat()
    user_doc = {
        "id": user_id, "email": email, "passwordHash": hash_password("dev-no-password"),
        "role": role, "createdAt": now, "updatedAt": now
    }
    company_doc = {
        "id": company_id, "type": role, "userId": user_id,
        "inn": "0000000000", "ogrn": "0000000000000",
        "companyName": f"DEV {role.title()}",
        "legalAddress": "DEV", "actualAddress": "DEV", "phone": "+70000000000",
        "email": email, "contractAccepted": True, "createdAt": now, "updatedAt": now
    }
    await db.users.insert_one(user_doc)
    await db.companies.insert_one(company_doc)
    if role == "supplier":
        await db.supplier_settings.insert_one({
            "id": str(uuid.uuid4()), "supplierCompanyId": company_id,
            "minOrderAmount": 0, "deliveryDays": [], "deliveryTime": "", "orderReceiveDeadline": "",
            "logisticsType": "own", "updatedAt": now
        })
    token = create_access_token({"sub": user_id, "role": role})
    return TokenResponse(
        access_token=token,
        user={"id": user_id, "email": email, "role": role, "companyId": company_id}
    )

# app/routes/finance.py
from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from typing import List, Optional, Literal, Union
from pydantic import BaseModel
from datetime import datetime

from app.db import get_session
from app.auth import get_current_api_admin_user
from app.models import FinanceEntry, Withdrawal, InventoryItem
from app.services import finance_calculator, inventory_manager

router = APIRouter(
    prefix="/api/admin",
    tags=["Finance API"],
    dependencies=[Depends(get_current_api_admin_user)]
)
html_router = APIRouter(
    prefix="/admin",
    tags=["Finance Page"],
    dependencies=[Depends(get_current_admin_user)]
)

templates = Jinja2Templates(directory="app/templates")

# --- Page serving ---
@html_router.get("/finance", response_class=HTMLResponse)
async def get_finance_page(request: Request):
    """Serves the main finance dashboard page."""
    return templates.TemplateResponse("admin/finance.html", {"request": request})

# --- Pydantic Models for API ---
class WithdrawalCreate(BaseModel):
    amount: float
    description: str
    withdrawal_type: Literal['cost_reimbursement', 'profit_draw', 'capital_expenditure', 'fixed_cost']
    inventory_item_sku: Optional[str] = None
    quantity_purchased: Optional[float] = None

class Transaction(BaseModel):
    timestamp: datetime
    description: str
    type: str
    amount: float
    is_withdrawal: bool
    order_id: Optional[int] = None

# --- API Endpoints ---
@router.get("/finance/summary")
def get_finance_summary(
    period: str = Query("month", description="Time period: 'today', 'week', 'month', 'quarter', 'year', 'all'"),
    session: Session = Depends(get_session)
):
    """API endpoint to provide a high-level summary for the finance dashboard."""
    return finance_calculator.get_dashboard_summary(session, period)

@router.get("/finance/transactions", response_model=List[Transaction])
def get_finance_transactions(
    period: str = Query("month", description="Time period: 'today', 'week', 'month', 'quarter', 'year', 'all'"),
    session: Session = Depends(get_session)
):
    """API endpoint to get a unified list of financial transactions (revenue and withdrawals)."""
    start_date = finance_calculator.get_start_date_for_period(period)
    
    revenue_entries = session.exec(
        select(FinanceEntry)
        .where(FinanceEntry.entry_type == 'revenue', FinanceEntry.timestamp >= start_date)
    ).all()
    
    withdrawals = session.exec(
        select(Withdrawal).where(Withdrawal.timestamp >= start_date)
    ).all()

    transactions = []
    for entry in revenue_entries:
        transactions.append(Transaction(
            timestamp=entry.timestamp,
            description=entry.description,
            type="Revenue",
            amount=entry.amount,
            is_withdrawal=False,
            order_id=entry.order_id
        ))
    
    for w in withdrawals:
        transactions.append(Transaction(
            timestamp=w.timestamp,
            description=w.description,
            type=w.withdrawal_type.replace('_', ' ').title(),
            amount=w.amount,
            is_withdrawal=True
        ))
        
    transactions.sort(key=lambda t: t.timestamp, reverse=True)
    return transactions

@router.post("/finance/withdrawals")
def record_withdrawal(
    withdrawal_data: WithdrawalCreate,
    session: Session = Depends(get_session)
):
    """Records a withdrawal from the business balance."""
    if withdrawal_data.withdrawal_type == 'cost_reimbursement':
        if not withdrawal_data.inventory_item_sku or not withdrawal_data.quantity_purchased:
            raise HTTPException(status_code=400, detail="Inventory item and quantity are required for cost reimbursements.")

    new_withdrawal = Withdrawal.from_orm(withdrawal_data)
    session.add(new_withdrawal)
    session.commit()
    session.refresh(new_withdrawal)

    feedback_message = "Withdrawal recorded successfully."
    if new_withdrawal.withdrawal_type == 'cost_reimbursement':
        feedback_message = inventory_manager.add_stock_from_withdrawal(new_withdrawal, session)
    
    return JSONResponse(content={"message": feedback_message})

@router.get("/inventory/summary", response_model=List[InventoryItem])
def get_inventory_summary(session: Session = Depends(get_session)):
    """Gets the status of all tracked inventory items."""
    return session.exec(select(InventoryItem)).all()
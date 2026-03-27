# app/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from app.calculator import calculate_overcurrent_protection

app = FastAPI()

class InputData(BaseModel):
    current_max: float
    k_n: float = 1.2
    k_r: float = 1.1
    k_z: float = 0.9

@app.post("/calculate-overcurrent/")
async def calc(data: InputData):
    result = calculate_overcurrent_protection(
        data.current_max,
        data.k_n,
        data.k_r,
        data.k_z
    )
    return {"setting": result}

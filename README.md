# AdaptiveGridBot

**AdaptiveGridBot** คือเฟรมเวิร์กการเทรดแบบกริดเชิงอัลกอริทึมสำหรับการทดลอง พัฒนากลยุทธ์ การทดสอบกลยุทธ์ และการทำ Backtest แบบหลายรุ่น โดยภายใน Repository ประกอบด้วยเอนจินประมวลผลหลัก ระบบจัดการความเสี่ยง Dashboard สำหรับติดตามแบบเรียลไทม์บนเว็บ รวมถึงสคริปต์สำหรับ Backtest และการทดลองเทรดแบบ Paper Trading จำนวนมาก

---

## ความสามารถหลัก

- **เอนจิน Adaptive Grid Trading**: คำนวณและปรับระยะห่างของ Grid ขอบเขตคำสั่ง และระดับ Position แบบไดนามิกตามความผันผวนของตลาดและ Indicator
- **การจัดการข้อมูลตลาด**: ดึงข้อมูลตลาดย้อนหลัง ประมวลผลแท่งเทียน OHLCV คำนวณ Indicator และรับราคาตลาดแบบเรียลไทม์
- **Grid Engine และ Order Management**: จัดการการสร้างคำสั่ง Grid ตามสถานะ ติดตามการยกเลิกคำสั่ง ตรวจจับการจับคู่คำสั่ง และจัดการกระบวนการส่งคำสั่ง
- **ระบบบริหารความเสี่ยง**: ตรวจสอบ Drawdown จำกัด Position ตรวจสอบเพดาน Exposure และรองรับกลไก Stop-Loss
- **การติดตามบัญชีและ Portfolio**: ติดตามยอดคงเหลือ ตรวจสอบ Margin และติดตาม Portfolio ของคู่เทรดที่กำลังทำงาน
- **Dashboard แบบเรียลไทม์**: มี HTTP Dashboard ในตัว (adaptive_grid_dashboard.py) สำหรับติดตาม Grid ที่กำลังทำงาน คำสั่งที่เปิดอยู่ Equity และข้อมูลประสิทธิภาพ
- **ชุดเครื่องมือ Backtesting ครบชุด**: รองรับ Backtest การวิเคราะห์ Realized PnL การตรวจสอบ Edge การทดสอบ Walk-Forward และการ Optimization ของ Parameter
- **Demo / Paper Trading**: มี Demo Loop และ Paper-Trading Runner แบบแยกส่วนสำหรับทดสอบกลยุทธ์โดยไม่ใช้เงินจริง

---

## สถาปัตยกรรม

    ┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
    │   Market Data   │ ──► │ Indicators / Strategy│ ──► │   Grid Engine   │
    └─────────────────┘     └──────────────────────┘     └─────────────────┘
                                                                  │
    ┌─────────────────┐     ┌──────────────────────┐              ▼
    │    Dashboard /  │ ◄── │    Exchange / Demo   │ ◄── ┌─────────────────┐
    │   Monitoring    │     │   (Execution Layer)  │     │   Risk Engine   │
    └─────────────────┘     └──────────────────────┘     └─────────────────┘
                                      ▲                           │
                                      └──── ┌─────────────────┐ ──┘
                                            │  Order Manager  │
                                            └─────────────────┘

### โมดูลหลัก

- **market_data.py**: รับข้อมูลราคา โหลดข้อมูลย้อนหลัง และจัดการเครื่องมือวิเคราะห์ทางเทคนิค
- **grid_engine.py**: โมเดลคณิตศาสตร์หลักสำหรับสร้างระดับ Grid ปรับระยะห่างแบบไดนามิก และสร้างโครงสร้างคำสั่ง
- **order_manager.py**: ประสานงานการส่งคำสั่ง ตรวจสอบสถานะ ตรวจสอบการจับคู่คำสั่ง และการยกเลิกคำสั่ง
- **risk_engine.py**: บังคับใช้กฎด้านความปลอดภัย จำกัด Exposure ตรวจสอบ Drawdown และรองรับ Emergency Halt
- **account_manager.py**: ติดตามยอดคงเหลือของบัญชี สุขภาพของ Margin และสถิติ Position
- **adaptive_grid_dashboard.py**: Web Interface แบบไฟล์เดียวสำหรับแสดง Telemetry, Grid ที่กำลังทำงาน และกราฟประสิทธิภาพ

---

## รุ่นของกลยุทธ์

Repository นี้บันทึกวิวัฒนาการของ Adaptive Grid Strategy ผ่านการทดลองหลายรุ่น:

- **การทดลองระยะแรก (v0.1 – v0.4)**: Prototype ของ Grid Engine ระบบระยะห่างแบบคงที่ และชุด Backtest พื้นฐาน เช่น grid_bot_v02.py, adaptive_grid_v04.py
- **Generation 4.8 (v0.4.8 / v4.8)**: เพิ่ม Smart Loop Execution การกำหนดขนาด Position ตาม Risk Cap และการติดตาม Realized PnL เช่น adaptive_grid_v048_demo_smart_loop.py, eth_grid_engine_v048.py
- **Generation 4.9 (v0.4.9 / v4.9)**: รองรับหลายสินทรัพย์ ปรับปรุง Cadence Control และปรับปรุง Order Manager เช่น adaptive_grid_v049_boss_demo_smart_loop.py, sol_order_manager_v049.py
- **Generation 5.0 (v0.5.0 / v5.0)**: เพิ่ม Candidate Filtering, โมเดล Walk-Forward Validation และการติดตาม Persistent Grid State
- **Generation 5.1 (v0.5.1 / v0.5.1.1)**: เพิ่ม Persistent Grid แบบเต็มรูปแบบ เครื่องมือจำลอง Fill และสคริปต์ Multi-Walk-Forward Optimization เช่น adaptive_grid_v0511_demo_smart_loop_FULL.py

*หมายเหตุ: Repository มีหลาย Variant สำหรับการทดลองและ Demo ซึ่งสะท้อนพัฒนาการในแต่ละช่วง ไม่มี Version ใดถูกกำหนดให้เหนือกว่าทุก Version สำหรับทุกกรณี*

---

## ตลาดที่รองรับ / ทดสอบ

ใน Codebase มี Configuration, Backtest Script และ Demo Bot Variant ที่ออกแบบสำหรับ:

- **Bitcoin (BTC)**: เช่น adaptive_grid_bot_A_btc.py, adaptive_grid_bot_B_btc.py, adaptive_grid_bot_C_btc.py
- **Ethereum (ETH)**: เช่น adaptive_grid_bot_D_eth.py, eth_adaptive_grid_v049_demo_smart_loop.py, eth_backtest_v048.py
- **Solana (SOL)**: เช่น adaptive_grid_bot_G_sol.py, sol_adaptive_grid_v049_demo_smart_loop.py, adaptive_grid_v048_sol_G_demo_smart_loop.py

---

## ชุด Backtesting และการวิเคราะห์

ส่วนสำคัญของ Repository คือชุดเครื่องมือสำหรับ Backtest และการวิเคราะห์:

- **backtest_v048_realized_pnl.py**: ประเมินการกระจายของ Realized PnL และประสิทธิภาพการเกิด Grid Fill
- **backtest_v047_edge_analysis.py**: ตรวจสอบ Edge ทางสถิติในสภาวะตลาดที่มีความผันผวนแตกต่างกัน
- **backtest_v050_multi_walkforward.py**: ทดสอบ Walk-Forward หลายช่วงเวลาเพื่อช่วยตรวจจับ Curve Fitting
- **backtest_v05_30d_optimizer_DOWNLOAD.py**: Optimization ของ Parameter แบบอัตโนมัติบนช่วงข้อมูลตลาดย้อนหลัง
- **eth_backtest_validate_v049.py**: Runner สำหรับตรวจสอบ Configuration ของ Ethereum แบบ Out-of-Sample
- **backtest_v045_riskcap.py**: โมดูล Stress Test สำหรับ Exposure และ Drawdown ที่มี Risk Cap

---

## Dashboard และการ Monitoring

Repository มี adaptive_grid_dashboard.py ซึ่งเป็น Web Dashboard น้ำหนักเบาสำหรับแสดง Monitoring Panel แบบเรียลไทม์ โดยแสดงข้อมูล:

- Visualisation ของสถานะ Grid (ขอบเขตบน/ล่าง เส้น Grid ที่ใช้งาน และ Current Index)
- ตารางคำสั่งที่เปิดอยู่และประวัติ Fill พร้อมการ Reconciliation
- Equity Curve ของบัญชี และรายละเอียด Unrealized / Realized PnL
- สุขภาพของระบบ Telemetry ของ API Latency และ Log Streaming

สคริปต์รายงานเพิ่มเติม เช่น okx_demo_report_v05.py และ backtest_report.py ใช้สร้างสรุปผลเพิ่มเติม

---

## เริ่มต้นใช้งาน

### สิ่งที่ต้องมีและการติดตั้ง

1. **Clone Repository**:

    git clone https://github.com/tanma2008/AdaptiveGridBot.git
    cd AdaptiveGridBot

2. **สร้าง Virtual Environment**:
   - **Windows**:

        python -m venv .venv
        .venv\Scripts\activate

   - **Linux / macOS**:

        python3 -m venv .venv
        source .venv/bin/activate

3. **ติดตั้ง Dependencies**:
   หาก Script ที่ต้องการใช้งานมีไฟล์ Requirements เฉพาะ เช่น requirements_v048.txt ให้ติดตั้งด้วย:

        pip install -r requirements_v048.txt

   *Dependencies มาตรฐานโดยทั่วไปประกอบด้วย requests, pandas, numpy และ Library สำหรับข้อมูลตลาด / Exchange API*

---

## Configuration และความปลอดภัย

- **API Credentials**: ห้ามใส่ API Key, Secret Key หรือ Password ลงใน Script โดยตรง หรือ Push ขึ้น Public Repository
- **Environment Variables**: ใช้ไฟล์ Configuration ภายนอก Environment Variable หรือ Credential Store ที่ปลอดภัยสำหรับส่ง Credentials ตอน Runtime
- **Dry-Run Default**: ควรทดสอบกลยุทธ์ในโหมด Paper Trading / Demo ก่อนเชื่อมต่อกับเงินจริงเสมอ

---

## โครงสร้างโปรเจกต์โดยสรุป

    AdaptiveGridBot/
    ├── market_data.py                    # รับข้อมูลตลาดและประมวลผล Indicator
    ├── grid_engine.py                    # สร้างระดับ Grid และปรับแบบไดนามิก
    ├── order_manager.py                  # วงจรชีวิตคำสั่งและการ Reconcile สถานะ
    ├── risk_engine.py                    # Risk Limit, Exposure Cap และ Safety Halt
    ├── account_manager.py                # ติดตามยอดคงเหลือและสถานะ Margin
    ├── adaptive_grid_dashboard.py        # Web Telemetry และ Monitoring Dashboard
    ├── adaptive_grid_bot_A_btc.py        # BTC Bot Variant สำหรับการทดลอง
    ├── adaptive_grid_bot_D_eth.py        # ETH Bot Variant สำหรับการทดลอง
    ├── adaptive_grid_bot_G_sol.py        # SOL Bot Variant สำหรับการทดลอง
    ├── adaptive_grid_v048_demo_smart_loop.py # Smart Loop Runner รุ่น 4.8
    ├── adaptive_grid_v0511_demo_smart_loop_FULL.py # Implementation เต็มรูปแบบรุ่น 5.1.1
    ├── backtest_v048_realized_pnl.py     # โมดูล Backtest Realized PnL
    ├── backtest_v050_multi_walkforward.py# เอนจิน Walk-Forward Optimization
    ├── requirements_v048.txt             # ตัวอย่าง Dependency Manifest
    └── ...

---

## สถานะการพัฒนา

Repository นี้เป็น **พื้นที่สำหรับการวิจัยและการทดลองที่ยังมีการพัฒนาอยู่** ภายในมี Script ย้อนหลัง Prototype, Backtest หลาย Variant และ Experimental Variant ที่สะสมจากการพัฒนาหลายรอบ โครงสร้าง Code และ Parameter ของแต่ละ Script จึงสะท้อน Configuration เฉพาะของการทดลองในแต่ละช่วง

---

## การพัฒนาด้วย AI

บางส่วนของ Codebase, Framework สำหรับ Backtesting และ Component ทางสถาปัตยกรรม ได้รับการออกแบบ ปรับปรุง และจัดทำเอกสารด้วยเครื่องมือ AI และ Workflow สำหรับการเขียนโค้ดแบบอัตโนมัติ

---

## ใบอนุญาตและข้อจำกัดความรับผิดชอบ

### ข้อจำกัดความรับผิดชอบ

> **โปรเจกต์นี้จัดทำขึ้นเพื่อการวิจัย การทดลอง การทำ Backtest และการศึกษาเท่านั้น**
>
> การเทรดแบบอัลกอริทึมและตลาด Cryptocurrency มีความเสี่ยงทางการเงินสูง ผู้เขียนและผู้มีส่วนร่วมไม่รับผิดชอบต่อความสูญเสียทางการเงิน พฤติกรรมที่ไม่คาดคิดของ Bot หรือข้อผิดพลาดในการส่งคำสั่ง ผู้ใช้งานมีหน้าที่ตรวจสอบ API Credentials, Risk Limit, Configuration และการตัดสินใจในการเทรดของตนเอง

### License

License: ยังไม่ได้ระบุ

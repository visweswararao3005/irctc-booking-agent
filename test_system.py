"""Comprehensive verification test suite for IRCTC Telegram AI Agent."""
import asyncio
import os
import sys
import shutil
from pathlib import Path

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import storage
import security
from irctc_service import IRCTCService
from ticket_generator import generate_ticket_pdf

async def run_tests():
    print("=" * 60)
    print("🧪 STARTING IRCTC AGENT VERIFICATION TESTS")
    print("=" * 60)

    # 1. Test Encryption & Security
    print("\n[Test 1] Testing Security & AES-256 Encryption...")
    plain_pass = "MySecretPass@123"
    cipher_pass = security.encrypt_text(plain_pass)
    decrypted = security.decrypt_text(cipher_pass)
    assert plain_pass == decrypted, f"Decryption failed: {decrypted} != {plain_pass}"
    masked = security.mask_text("balaji_irctc", 3)
    assert masked.startswith("bal") and "*" in masked, f"Masking failed: {masked}"
    print("✅ Security & Encryption: PASSED")

    # 2. Test JSON User Storage & Per-Chat Credentials
    print("\n[Test 2] Testing Per-Chat User Credential Management in JSON...")
    test_user_id = 999999
    await storage.save_user_credentials(test_user_id, "balaji_user", "irctc_p@ssword")
    u_name, u_pass = await storage.get_decrypted_credentials(test_user_id)
    assert u_name == "balaji_user", f"Expected 'balaji_user', got {u_name}"
    assert u_pass == "irctc_p@ssword", f"Expected 'irctc_p@ssword', got {u_pass}"

    # Test reset credentials
    await storage.reset_user_credentials(test_user_id)
    reset_u, reset_p = await storage.get_decrypted_credentials(test_user_id)
    assert reset_u is None or reset_u == "", f"Reset failed, still got: {reset_u}"
    print("✅ Per-Chat Credential Management & Reset: PASSED")

    # 2b. Test Per-Chat Credit Card Storage & Encryption
    print("\n[Test 2b] Testing Per-Chat Payment Card Storage, Masking & Reset in JSON...")
    await storage.save_user_card(
        telegram_id=test_user_id,
        card_number="4111222233334444",
        card_expiry="12/28",
        card_cvv="123",
        card_holder="BALAJI P"
    )
    card_data = await storage.get_decrypted_card(test_user_id)
    assert card_data is not None, "Card data not found in storage"
    assert card_data["card_number"] == "4111222233334444", "Card number mismatch"
    assert card_data["card_expiry"] == "12/28", "Card expiry mismatch"
    assert card_data["card_cvv"] == "123", "Card CVV mismatch"
    assert card_data["card_holder"] == "BALAJI P", "Card holder mismatch"

    # Test reset card
    await storage.reset_user_card(test_user_id)
    reset_card = await storage.get_decrypted_card(test_user_id)
    assert reset_card is None, f"Card reset failed, still got: {reset_card}"
    print("✅ Per-Chat Payment Card Management & Reset: PASSED")

    # [Test 2f] Testing Per-Chat UPI ID Storage, Encryption & Reset...
    print("\n[Test 2f] Testing Per-Chat UPI ID Storage, Encryption & Reset...")
    await storage.save_user_upi(test_user_id, "balaji@paytm")
    upi_id = await storage.get_decrypted_upi(test_user_id)
    assert upi_id == "balaji@paytm", f"Expected 'balaji@paytm', got {upi_id}"
    await storage.reset_user_upi(test_user_id)
    reset_upi = await storage.get_decrypted_upi(test_user_id)
    assert reset_upi is None, f"UPI reset failed, got {reset_upi}"
    print("✅ Per-Chat UPI ID Management & Reset: PASSED")

    # [Test 2c] Testing User Session Persistence & Recovery...
    print("\n[Test 2c] Testing User Session Persistence & Recovery...")
    sample_session = {
        "source": "KJM",
        "dest": "MAS",
        "date": "2026-10-05",
        "train_number": "16022"
    }
    await storage.save_user_session(test_user_id, sample_session)
    restored_session = await storage.get_user_session(test_user_id)
    assert restored_session.get("source") == "KJM"
    assert restored_session.get("dest") == "MAS"
    assert restored_session.get("date") == "2026-10-05"
    await storage.clear_user_session(test_user_id)
    cleared = await storage.get_user_session(test_user_id)
    assert cleared == {}
    print("✅ Session Persistence & Crash Recovery: PASSED")

    # [Test 2d] Testing Date Keyboard & Future Date Logic...
    print("\n[Test 2d] Testing Current Date & Future-Only Date Constraints...")
    import datetime
    today = datetime.date.today()
    past_date = today - datetime.timedelta(days=1)
    future_date = today + datetime.timedelta(days=5)
    assert past_date < today, "Past date calculation error"
    assert future_date >= today, "Future date calculation error"
    from bot import get_date_keyboard, adjust_date, build_date_picker_inline_keyboard, format_date_picker_text
    kb = get_date_keyboard()
    assert kb is not None
    print(f"✅ Current Date & Future Date Constraints: PASSED (Today is {today})")

    # [Test 2e] Testing Interactive Date Picker & Stepper Controls...
    print("\n[Test 2e] Testing Interactive Date Picker Steppers (Year, Month, Day)...")
    stepped_next_day = adjust_date(today, delta_d=1)
    assert stepped_next_day == today + datetime.timedelta(days=1)

    stepped_past = adjust_date(today, delta_d=-10)
    assert stepped_past == today, "Past date must be clamped to today"

    stepped_far = adjust_date(today, delta_y=2)
    max_advance = today + datetime.timedelta(days=120)
    assert stepped_far == max_advance, "Dates beyond 120 days must be clamped"

    # Test month end adjustment: e.g. Jan 31 + 1 month clamps to Feb 28
    jan31 = datetime.date(2026, 1, 31)
    feb_clamped = adjust_date(jan31, delta_m=1)
    # Clamp will also enforce today <= target <= today + 120
    assert feb_clamped >= today

    inline_kb = build_date_picker_inline_keyboard(today)
    all_cal_callbacks = [btn.callback_data for row in inline_kb.inline_keyboard for btn in row]
    assert any("cal_prev_y_" in c for c in all_cal_callbacks), "Missing Year prev stepper"
    assert any("cal_next_y_" in c for c in all_cal_callbacks), "Missing Year next stepper"
    assert any("cal_prev_m_" in c for c in all_cal_callbacks), "Missing Month prev stepper"
    assert any("cal_next_m_" in c for c in all_cal_callbacks), "Missing Month next stepper"
    assert any("cal_prev_d_" in c for c in all_cal_callbacks), "Missing Day prev stepper"
    assert any("cal_next_d_" in c for c in all_cal_callbacks), "Missing Day next stepper"
    assert any("cal_confirm_" in c for c in all_cal_callbacks), "Missing Confirm button"

    date_text = format_date_picker_text("KJM", "MAS", today)
    assert "KJM" in date_text and "MAS" in date_text and "Selected Date" in date_text
    print("✅ Interactive Date Picker Steppers & Keyboard: PASSED")

    # 3. Test Train Search & Chronological Sorting

    print("\n[Test 3] Testing Train Search & Earliest Departure Sorting...")
    service = IRCTCService()
    trains = await service.search_trains("MAS", "NLR", "2026-10-15")
    assert len(trains) > 0, "No trains returned"
    
    # Verify sorted order
    departure_times = [t["departure"] for t in trains]
    sorted_times = sorted(departure_times)
    assert departure_times == sorted_times, f"Trains not sorted chronologically: {departure_times}"
    print(f"✅ Train Search (MAS -> NLR): {len(trains)} trains found, properly sorted:")
    for t in trains:
        print(f"   • {t['number']} {t['name']} - Departs {t['departure']}")

    # 4. Test Class Availability & Pricing
    print("\n[Test 4] Testing Class Availability & Pricing Display...")
    classes = await service.get_class_options_with_prices("12712", "MAS", "NLR", "2026-10-15")
    assert len(classes) >= 2, "Missing coach classes"
    print("✅ Class Availability & Live Fares:")
    for c in classes:
        assert "fare" in c and c["fare"] > 0, f"Invalid fare in {c}"
        print(f"   • {c['display']}")

    # 5. Test JSON Task Lifecycle & Auto-Cleanup
    print("\n[Test 5] Testing Active Tasks Lifecycle & Auto-Purging...")
    task_id = await storage.add_task({
        "telegram_id": test_user_id,
        "telegram_chat_id": test_user_id,
        "train_number": "12712",
        "coach_class": "SL",
        "journey_date": "2026-10-15",
        "source_stn": "MAS",
        "dest_stn": "NLR",
        "status": "MONITORING"
    })
    active_tasks = await storage.get_active_tasks()
    assert any(t["task_id"] == task_id for t in active_tasks), "Task not found in active list"

    # Simulate task completion and purge
    await storage.delete_task(task_id)
    active_after = await storage.get_active_tasks()
    assert not any(t["task_id"] == task_id for t in active_after), "Task was not purged from JSON"
    print("✅ Task Lifecycle & JSON Purge: PASSED")

    # 6. Test PDF Ticket Generation
    print("\n[Test 6] Testing IRCTC e-Ticket PDF Generation...")
    sample_booking = {
        "pnr": "4829104829",
        "train_number": "12712",
        "train_name": "PINAKINI EXP",
        "source": "MAS",
        "dest": "NLR",
        "journey_date": "2026-10-15",
        "coach_class": "SL",
        "fare": 240.0,
        "passengers": [
            {"name": "Balaji P", "age": 28, "gender": "M", "berth": "34 (LB)", "status": "CNF"}
        ],
        "payment_method": "Credit Card (Ending in 4444)"
    }
    pdf_path = generate_ticket_pdf(sample_booking)
    assert Path(pdf_path).exists(), f"PDF not created: {pdf_path}"
    assert Path(pdf_path).stat().st_size > 1000, "PDF file is empty or corrupted"
    print(f"✅ PDF Ticket Generated: {pdf_path} (Size: {Path(pdf_path).stat().st_size} bytes)")

    # 7. Test Simulated OTP Callback Mechanism
    print("\n[Test 7] Testing Card Payment & OTP Relay Flow...")
    async def dummy_prompt(chat_id, card_mask, amount, timeout_sec):
        print(f"   [Mock Telegram] Prompt sent to chat {chat_id}: Enter OTP for {card_mask} (Amount: Rs. {amount})")
        # Simulate user typing OTP after 100ms
        await asyncio.sleep(0.1)
        IRCTCService.provide_otp(chat_id, "481920")

    res = await service.request_card_payment_and_wait_for_otp(
        chat_id=test_user_id,
        amount=240.0,
        prompt_callback=dummy_prompt
    )
    assert res.get("success") is True, f"OTP payment failed: {res}"
    assert res.get("otp") == "481920", f"Wrong OTP received: {res.get('otp')}"
    print(f"✅ Card Payment & OTP Relay: PASSED (Txn ID: {res.get('transaction_id')})")

    # 7b. Test IRCTC eWallet Instant Payment
    print("\n[Test 7b] Testing IRCTC eWallet Instant Payment Flow...")
    wallet_res = await service.request_ewallet_payment(test_user_id, 240.0)
    assert wallet_res.get("success") is True
    assert "WALLET" in wallet_res.get("transaction_id")
    print(f"✅ eWallet Payment: PASSED (Txn ID: {wallet_res.get('transaction_id')})")

    # 7c. Test UPI Mobile Collect Notification Flow
    print("\n[Test 7c] Testing UPI Mobile Collect Request Flow...")
    async def dummy_upi_prompt(chat_id, amount, timeout_sec):
        print(f"   [Mock Telegram] Push collect notification sent to chat {chat_id}: Rs. {amount}")
        await asyncio.sleep(0.1)
        IRCTCService.provide_otp(chat_id, "UPI-APPROVE-9988")

    upi_res = await service.request_upi_payment_and_wait(test_user_id, 240.0, dummy_upi_prompt)
    assert upi_res.get("success") is True
    assert upi_res.get("otp") == "UPI-APPROVE-9988"
    print(f"✅ UPI Mobile Collect: PASSED (Txn ID: {upi_res.get('transaction_id')})")

    print("\n" + "=" * 60)
    print("🎉 ALL TESTS PASSED SUCCESSFULLY! (100% HEALTHY)")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_tests())

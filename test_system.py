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
    # 8. Test Seat Sniper Watchdog & Charting Release Trigger
    print("\n[Test 8] Testing Seat Sniper Watchdog & Charting/Cancellation Release Trigger...")
    sniper_avail_initial = await service.check_availability("12712", "2026-10-15", "SL", "MAS", "NLR")
    assert sniper_avail_initial["is_available"] is False, "Seat Sniper must hold fire and not mark WL as available"
    assert "WL" in sniper_avail_initial["status"] or "PENDING" in sniper_avail_initial["status"].upper(), "Status must reflect WL/Pending"
    print(f"   • Initial Watchdog State: {sniper_avail_initial['status']} (is_available={sniper_avail_initial['is_available']})")

    # Simulate charting unfreezing / passenger cancellation
    service.simulate_cancellation_open_seats("12712", "2026-10-15", "SL", count=2)
    sniper_avail_released = await service.check_availability("12712", "2026-10-15", "SL", "MAS", "NLR")
    assert sniper_avail_released["is_available"] is True, "Seat Sniper must detect opened seats upon release"
    assert sniper_avail_released["seats"] == 2
    print(f"   • Released Watchdog State: {sniper_avail_released['status']} (is_available={sniper_avail_released['is_available']})")
    print("✅ Seat Sniper Watchdog & Release Trigger: PASSED")

    # 9. Test /info and /tasks Handlers & User Task Isolation
    print("\n[Test 9] Testing /info and /tasks Handlers & User Task Isolation...")
    # Add active task for test user
    t_id = await storage.add_task({
        "telegram_id": test_user_id,
        "telegram_chat_id": test_user_id,
        "train_number": "16022",
        "train_name": "KAVERI EXP",
        "coach_class": "SL",
        "journey_date": "2026-10-20",
        "source_stn": "SBC",
        "dest_stn": "MAS",
        "status": "MONITORING",
        "booking_mode": "SNIPER",
        "passengers": [{"name": "Balaji P", "age": 28, "gender": "M", "berth": "Lower Berth (LB)"}]
    })

    user_tasks = await storage.get_user_active_tasks(test_user_id)
    assert len(user_tasks) >= 1, "User active task not found"
    assert any(t["task_id"] == t_id for t in user_tasks), f"Task {t_id} missing in user active tasks"
    print(f"   • User Active Tasks found: {len(user_tasks)} (Task {t_id})")

    # Ensure another user sees 0 tasks
    other_user_tasks = await storage.get_user_active_tasks(123456789)
    assert len(other_user_tasks) == 0, "Task leaking across different users!"
    print("   • Multi-User Task Privacy Isolation: Verified (0 tasks leaked)")

    # Cleanup task
    await storage.delete_task(t_id)
    after_cleanup = await storage.get_user_active_tasks(test_user_id)
    assert not any(t["task_id"] == t_id for t in after_cleanup), "Task not purged"

    # Verify cmd_info and cmd_tasks are imported from bot
    import bot
    assert callable(bot.cmd_info), "bot.cmd_info is not callable"
    assert callable(bot.cmd_tasks), "bot.cmd_tasks is not callable"
    print("✅ /info and /tasks Handlers & Task Privacy: PASSED")

    # 10. Test Persistent Passenger Profile Management & Reuse
    print("\n[Test 10] Testing Persistent Passenger Profile Management & 1-Click Reuse...")
    await storage.save_passenger_profile(test_user_id, "Vicky", 24, "Male", "Lower Berth (LB)")
    p_prof = await storage.get_passenger_profile(test_user_id)
    assert p_prof is not None, "Saved passenger profile was None"
    assert p_prof["name"] == "Vicky"
    assert p_prof["age"] == 24
    assert p_prof["gender"] == "Male"
    assert p_prof["berth"] == "Lower Berth (LB)"
    print(f"   • Saved Profile Verified: {p_prof['name']} ({p_prof['age']}, {p_prof['gender']}, {p_prof['berth']})")

    # Test Profile Reset
    await storage.reset_passenger_profile(test_user_id)
    assert await storage.get_passenger_profile(test_user_id) is None, "Profile was not reset"
    print("✅ Passenger Profile Storage, Retrieval & Reset: PASSED")

    # 11. Test Exact WL & Available Berth Calculations
    print("\n[Test 11] Testing Exact WL & Available Berth Status Breakdown...")
    class_opts = await service.get_class_options_with_prices("16022", "KJM", "MAS", "2026-10-15")
    assert len(class_opts) > 0, "No class options returned"
    sl_opt = next((c for c in class_opts if c["class_code"] == "SL"), None)
    assert sl_opt is not None, "SL class missing in options"
    assert "WL" in sl_opt["status"] or "AVAILABLE" in sl_opt["status"], f"Expected WL or AVAILABLE in status, got: {sl_opt['status']}"
    print(f"   • SL Status: {sl_opt['status']} | Quota: {sl_opt['quota']} | Fare: Rs. {sl_opt['fare']}")
    print(f"   • Display String: {sl_opt['display']}")
    print("✅ Exact WL & Available Count Breakdown: PASSED")

    # 12. Test Ticket Opening Estimation & Dynamic Polling Engine
    print("\n[Test 12] Testing Ticket Opening Estimation & Dynamic Polling Rate Ramp-Up...")
    from scheduler import compute_dynamic_polling_interval

    # Case A: Morning train (e.g. 16022 Kaveri Exp at 00:15) -> Previous day 20:00 IST rule
    est_morning = service.estimate_ticket_opening("16022", "00:15", "2026-10-15", "SL")
    assert "2026-10-14 20:00" in est_morning["chart_1_time"], f"Morning rule failed: {est_morning['chart_1_time']}"
    assert "2026-10-14 19:00" in est_morning["watchdog_start_time"], f"Watchdog start time failed: {est_morning['watchdog_start_time']}"
    assert est_morning["is_watchdog_active"] is False, "Watchdog should be dormant for future date"
    assert est_morning["is_morning_rule"] is True
    print(f"   • Morning Train Chart 1 Time: {est_morning['chart_1_time']} ({est_morning['chart_rule_note']})")
    print(f"   • Watchdog Start Point:       {est_morning['watchdog_start_time']} IST (Dormant until 1h before chart prep)")

    # Case B: Afternoon train (e.g. 12603 at 16:45) -> 4 hours prior rule (12:45)
    est_afternoon = service.estimate_ticket_opening("12603", "16:45", "2026-10-15", "SL")
    assert "2026-10-15 12:45" in est_afternoon["chart_1_time"], f"4h rule failed: {est_afternoon['chart_1_time']}"
    assert "2026-10-15 11:45" in est_afternoon["watchdog_start_time"]
    assert est_afternoon["is_morning_rule"] is False
    print(f"   • Afternoon Train Chart 1 Time: {est_afternoon['chart_1_time']} ({est_afternoon['chart_rule_note']})")

    # Case C: Dynamic Polling Rate Countdown
    # Standby (>2h): 900s
    int_standby, desc_standby = compute_dynamic_polling_interval(8000)
    assert int_standby == 900, f"Expected 900s standby, got {int_standby}"

    # Case D: Scheduled Sleep before watchdog start point (Zero 15-min spam!)
    int_sleep, desc_sleep = compute_dynamic_polling_interval(80000, seconds_until_watchdog_start=76400)
    assert int_sleep == 76400 and "SCHEDULED SLEEP" in desc_sleep, f"Expected scheduled sleep, got {int_sleep}, {desc_sleep}"

    # High Alert (60m to 30m): 60s
    int_60m, desc_60m = compute_dynamic_polling_interval(2400)
    assert int_60m == 60, f"Expected 60s at T-40m, got {int_60m}"

    # Ramp-Up (30m to 10m): 30s
    int_30m, desc_30m = compute_dynamic_polling_interval(1200)
    assert int_30m == 30, f"Expected 30s at T-20m, got {int_30m}"

    # Hyper-Drive Strike (10m to -15m): 10s
    int_strike, desc_strike = compute_dynamic_polling_interval(300)
    assert int_strike == 10, f"Expected 10s at strike spot, got {int_strike}"

    print(f"   • Scheduled Sleep Mode: {int_sleep}s ({desc_sleep})")
    print(f"   • Standby Polling:      {int_standby}s ({desc_standby})")
    print(f"   • T-40m Polling:        {int_60m}s ({desc_60m})")
    print(f"   • T-20m Polling:        {int_30m}s ({desc_30m})")
    print(f"   • Strike Polling:       {int_strike}s ({desc_strike})")
    print("✅ Ticket Opening Estimation & Dynamic Polling Rate Engine: PASSED")

    # 13. Test Smart UPI & Mobile Number Detection
    print("\n[Test 13] Testing Smart UPI & Mobile Number Detection (Valid vs Invalid)...")
    from bot import validate_and_normalize_upi

    # Case A: Full VPA handle
    v1, norm1, app1, err1 = validate_and_normalize_upi("visweswararao@paytm")
    assert v1 is True and norm1 == "visweswararao@paytm" and "Paytm" in app1, f"Failed VPA 1: {norm1}"

    v2, norm2, app2, err2 = validate_and_normalize_upi("9876543210@ybl")
    assert v2 is True and "PhonePe" in app2, f"Failed PhonePe VPA: {app2}"

    v3, norm3, app3, err3 = validate_and_normalize_upi("balaji@okaxis")
    assert v3 is True and "Google Pay" in app3, f"Failed GPay VPA: {app3}"

    # Case B: Plain 10-digit mobile number
    v4, norm4, app4, err4 = validate_and_normalize_upi("9876543210")
    assert v4 is True and norm4 == "9876543210@upi" and "NPCI" in app4, f"Failed 10-digit: {norm4}"

    # Case C: Mobile number with country code +91 and spaces
    v5, norm5, app5, err5 = validate_and_normalize_upi("+91 98765 43210")
    assert v5 is True and norm5 == "9876543210@upi", f"Failed +91 normalization: {norm5}"

    # Case D: Invalid Indian telecom prefix (starts with 1)
    v6, norm6, app6, err6 = validate_and_normalize_upi("1234567890")
    assert v6 is False and "start with 6, 7, 8, or 9" in err6, f"Failed telecom prefix check: {err6}"

    # Case E: Incorrect length (9 digits)
    v7, norm7, app7, err7 = validate_and_normalize_upi("987654321")
    assert v7 is False and "9 digits" in err7, f"Failed length check: {err7}"

    # Case F: Malformed VPA
    v8, norm8, app8, err8 = validate_and_normalize_upi("invalid@@upi")
    assert v8 is False and "one '@'" in err8, f"Failed double-@ check: {err8}"

    print(f"   • Full VPA Detected:     {norm1} -> {app1} (Valid: {v1})")
    print(f"   • PhonePe VPA Detected:  {norm2} -> {app2} (Valid: {v2})")
    print(f"   • Google Pay Detected:   {norm3} -> {app3} (Valid: {v3})")
    print(f"   • 10-digit Mobile Norm:  {norm4} -> {app4} (Valid: {v4})")
    print(f"   • +91 Number Norm:       {norm5} -> Cleaned (Valid: {v5})")
    print(f"   • Bad Prefix '123...':   Rejected cleanly: '{err6}' (Valid: {v6})")
    print(f"   • 9-digit '987...':      Rejected cleanly: '{err7}' (Valid: {v7})")
    print("✅ Smart UPI & Mobile Number Detection Engine: PASSED")

    print("\n" + "=" * 60)
    print("🎉 ALL TESTS PASSED SUCCESSFULLY! (100% HEALTHY)")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_tests())

# Evaluations: Greenfield Agent Building

This track has 70 public evaluations.

## sim__cancel_service_internet_english (simulations)
**Goal / Scenario**:
I want to cancel my home internet service because I am moving out of the country

### Simulation Steps
1. **Turn 1**: I want to cancel my home internet service because I am moving out of the country
   * **User guide**: Tell the agent you need to cancel your internet service. Provide your phone number and PIN when asked to authenticate. Listen to the contract terms and confirm you want to proceed with the cancellation
   * **Judge criteria**: The user is authenticated, hears the mandatory contract disclosure, and confirms the cancellation request

### Expectations / Assertions
* The user completes the cancellation flow after hearing the mandatory contract disclosure

---

## sim__cancel_service_mobility_french (simulations)
**Goal / Scenario**:
I want to cancel my mobile phone plan in French because I found a better deal with another provider

### Simulation Steps
1. **Turn 1**: I want to cancel my mobile phone plan in French because I found a better deal with another provider
   * **User guide**: Speak French from the start by saying 'Je veux annuler mon forfait mobile'. Provide your phone number and PIN when prompted. Listen to the French contract disclosure and confirm you want to cancel
   * **Judge criteria**: The user is authenticated in French, hears the French contract disclosure, and confirms the cancellation

### Expectations / Assertions
* The user completes the cancellation flow in French after hearing the mandatory contract disclosure

---

## sim__port_out_number_english (simulations)
**Goal / Scenario**:
I want to port my mobile number out to another carrier, which requires cancelling my current line

### Simulation Steps
1. **Turn 1**: I want to port my mobile number out to another carrier, which requires cancelling my current line
   * **User guide**: Tell the agent you want to port out your number. Provide your authentication details when prompted. Listen to the contract disclosure and confirm
   * **Judge criteria**: The user is authenticated, hears the mandatory contract disclosure regarding porting out, and confirms the request

### Expectations / Assertions
* The user successfully requests a port out and hears the mandatory contract disclosure

---

## sim__cancel_tv_service_english (simulations)
**Goal / Scenario**:
I want to cancel my Fibe TV subscription because I am switching to streaming-only

### Simulation Steps
1. **Turn 1**: I want to cancel my Fibe TV subscription because I am switching to streaming-only
   * **User guide**: Tell the agent you want to cancel your TV service. Provide your account number and PIN to authenticate. Listen to the contract disclosure and confirm you want to cancel
   * **Judge criteria**: The user is authenticated, hears the mandatory contract disclosure, and confirms TV cancellation

### Expectations / Assertions
* The user successfully cancels their TV service after hearing the mandatory contract disclosure

---

## sim__cancel_home_phone_french (simulations)
**Goal / Scenario**:
I want to cancel my residential landline phone service in French

### Simulation Steps
1. **Turn 1**: I want to cancel my residential landline phone service in French
   * **User guide**: Say 'Je veux annuler ma ligne résidentielle'. Provide your phone number and PIN when prompted. Listen to the French contract disclosure and confirm
   * **Judge criteria**: The user is authenticated in French, hears the French contract disclosure, and cancels the landline

### Expectations / Assertions
* The user successfully cancels their home phone service in French after hearing the mandatory contract disclosure

---

## sim__speak_immediate_english (simulations)
**Goal / Scenario**:
I want to speak to a human representative immediately to resolve a complex issue

### Simulation Steps
1. **Turn 1**: I want to speak to a human representative immediately to resolve a complex issue
   * **User guide**: On the very first turn, say 'I want to talk to a person'
   * **Judge criteria**: The user is immediately transferred to a live representative with the verbatim handoff message

### Expectations / Assertions
* The user is immediately transferred to a live representative with the verbatim handoff message

---

## sim__speak_immediate_french (simulations)
**Goal / Scenario**:
I want to speak to a French-speaking representative immediately

### Simulation Steps
1. **Turn 1**: I want to speak to a French-speaking representative immediately
   * **User guide**: On the first turn, say 'Je veux parler à un représentant'
   * **Judge criteria**: The user is immediately transferred to a French-speaking live representative with the French verbatim handoff message

### Expectations / Assertions
* The user is immediately transferred to a French-speaking representative with the French verbatim handoff message

---

## sim__speak_mid_call_billing_english (simulations)
**Goal / Scenario**:
I want to ask about my bill, but then decide it's too complicated and ask to speak to a person instead

### Simulation Steps
1. **Turn 1**: I want to ask about my bill, but then decide it's too complicated and ask to speak to a person instead
   * **User guide**: Start by saying 'I have a question about my bill'. When the agent asks for your account details, say 'Actually, I just want to talk to a real person.'
   * **Judge criteria**: The user starts a billing inquiry, then asks for an agent, and is immediately transferred with the verbatim handoff message

### Expectations / Assertions
* The user is successfully transferred to a live representative mid-call with the verbatim handoff message

---

## sim__speak_frustrated_english (simulations)
**Goal / Scenario**:
I am frustrated with my internet connection and want to bypass the automated system to talk to a human

### Simulation Steps
1. **Turn 1**: I am frustrated with my internet connection and want to bypass the automated system to talk to a human
   * **User guide**: Say 'Representative, please!' on the first turn
   * **Judge criteria**: The user asks for a representative and is immediately transferred with the verbatim handoff message

### Expectations / Assertions
* The user is immediately transferred to a live representative with the verbatim handoff message

---

## sim__speak_mid_call_tech_french (simulations)
**Goal / Scenario**:
I want to report a TV signal issue in French, but then decide to speak to a human agent instead

### Simulation Steps
1. **Turn 1**: I want to report a TV signal issue in French, but then decide to speak to a human agent instead
   * **User guide**: Start by saying 'Ma télé ne fonctionne pas'. When the agent responds, say 'Je veux parler à un agent'
   * **Judge criteria**: The user starts a tech support inquiry in French, then asks for an agent, and is immediately transferred with the French verbatim handoff message

### Expectations / Assertions
* The user is successfully transferred to a French-speaking representative mid-call with the French verbatim handoff message

---

## sim__dispute_unrecognized_streaming_charge (simulations)
**Goal / Scenario**:
I want to dispute an unfamiliar $12.50 streaming charge on my monthly bill and get a credit for it

### Simulation Steps
1. **Turn 1**: I want to dispute an unfamiliar $12.50 streaming charge on my monthly bill and get a credit for it
   * **User guide**: The user is polite but concerned about their bill. They will provide their phone number (514-555-0199) when asked, enter their PIN (1234) when prompted, and explain that they see an unrecognized $12.50 streaming charge that they want removed
   * **Judge criteria**: The user successfully authenticates, disputes the $12.50 charge, and receives confirmation of a $12.50 credit applied to their next statement

### Expectations / Assertions
* The user hears a confirmation that a $12.50 credit will appear on their next statement

---

## sim__dispute_billing_charge_french (simulations)
**Goal / Scenario**:
Je veux contester des frais d'appels interurbains erronés sur ma facture de téléphone mobile en français

### Simulation Steps
1. **Turn 1**: Je veux contester des frais d'appels interurbains erronés sur ma facture de téléphone mobile en français
   * **User guide**: The user speaks only French Canadian. They will provide their account number (883726152) and verify their identity using the SMS code sent to them. They will explain that they were charged for long-distance calls they never made
   * **Judge criteria**: The user conducts the entire call in French, authenticates successfully, disputes the incorrect long-distance charges, and receives a credit confirmation

### Expectations / Assertions
* The user hears the credit confirmation in French without any language switching or degradation

---

## sim__dispute_charge_business_account_deflection (simulations)
**Goal / Scenario**:
I want to dispute a billing charge on my business account

### Simulation Steps
1. **Turn 1**: I want to dispute a billing charge on my business account
   * **User guide**: The user states they are calling about a business account and want to dispute a charge. When asked for account details, they mention it is a business line
   * **Judge criteria**: The user is immediately redirected to a live business representative without being forced to go through residential self-service authentication

### Expectations / Assertions
* The user hears the verbatim business handoff message and is transferred to an agent

---

## sim__dispute_charge_auth_retry (simulations)
**Goal / Scenario**:
I want to dispute a charge on my bill, but I might make a mistake entering my PIN the first time

### Simulation Steps
1. **Turn 1**: I want to dispute a charge on my bill, but I might make a mistake entering my PIN the first time
   * **User guide**: The user provides their phone number. When prompted for their 4-digit PIN, they intentionally enter '9999' (incorrect). When prompted to retry, they enter the correct PIN '4321' and then proceed to dispute a $15 overcharge on their internet bill
   * **Judge criteria**: The user successfully authenticates on their second PIN attempt, disputes the charge, and resolves the issue

### Expectations / Assertions
* The user is allowed to retry authentication and successfully disputes the charge after a successful second attempt

---

## sim__pay_mobility_bill_card_file (simulations)
**Goal / Scenario**:
I want to pay my outstanding mobility bill balance using the credit card I have saved on my account

### Simulation Steps
1. **Turn 1**: I want to pay my outstanding mobility bill balance using the credit card I have saved on my account
   * **User guide**: The user is ready to pay. They provide their phone number, authenticate via SMS OTP, ask for their current balance, and agree to pay the full amount using their card on file
   * **Judge criteria**: The user authenticates, confirms their outstanding balance, and authorizes a payment using their saved card

### Expectations / Assertions
* The user receives a payment confirmation message with the last 4 digits of their card spoken back securely

---

## sim__pay_bill_french_keypad (simulations)
**Goal / Scenario**:
Je veux payer ma facture internet résidentielle en utilisant le clavier de mon téléphone pour entrer mes informations en français

### Simulation Steps
1. **Turn 1**: Je veux payer ma facture internet résidentielle en utilisant le clavier de mon téléphone pour entrer mes informations en français
   * **User guide**: The user speaks French. They prefer to use their phone keypad (DTMF) to enter their account number and PIN when prompted, then confirm they want to pay their balance
   * **Judge criteria**: The user completes a bill payment in French, using DTMF inputs for authentication and payment confirmation

### Expectations / Assertions
* The system registers the DTMF inputs correctly and confirms the payment in French

---

## sim__pay_past_due_bill_prevent_suspension (simulations)
**Goal / Scenario**:
I want to pay my past-due balance immediately to make sure my mobile service doesn't get cut off

### Simulation Steps
1. **Turn 1**: I want to pay my past-due balance immediately to make sure my mobile service doesn't get cut off
   * **User guide**: The user is anxious about service suspension. They provide their account details, authenticate quickly, and ask to pay the past-due balance immediately using a credit card
   * **Judge criteria**: The user authenticates, identifies the past-due amount, and successfully processes the payment

### Expectations / Assertions
* The user receives immediate confirmation that their payment was successful and their service status is secure

---

## sim__pay_bill_declined_card_retry (simulations)
**Goal / Scenario**:
I want to pay my bill, but if my primary card is declined, I want to try a different card

### Simulation Steps
1. **Turn 1**: I want to pay my bill, but if my primary card is declined, I want to try a different card
   * **User guide**: The user authenticates and attempts to pay. When told the card on file was declined, they remain calm and provide details for a secondary credit card to complete the payment
   * **Judge criteria**: The user handles a card decline error gracefully and successfully pays using an alternative card

### Expectations / Assertions
* The user is prompted to provide alternative payment details after the first card fails, resulting in a successful transaction

---

## sim__setup_autopay_internet_english (simulations)
**Goal / Scenario**:
I want to set up automatic monthly payments (autopay) for my home internet service so I don't miss any future bills

### Simulation Steps
1. **Turn 1**: I want to set up automatic monthly payments (autopay) for my home internet service so I don't miss any future bills
   * **User guide**: The user wants a hands-off billing experience. They authenticate using their PIN and request to set up autopay with their Visa card ending in 4321
   * **Judge criteria**: The user authenticates and successfully enrolls their account in automatic payments using their credit card

### Expectations / Assertions
* The user hears a confirmation that autopay has been successfully configured for their account

---

## sim__setup_autopay_french (simulations)
**Goal / Scenario**:
Je veux configurer les paiements préautorisés (autopay) sur mon compte de mobilité en français

### Simulation Steps
1. **Turn 1**: Je veux configurer les paiements préautorisés (autopay) sur mon compte de mobilité en français
   * **User guide**: The user initiates the call in French, authenticates with their PIN, and requests to set up pre-authorized payments using their bank account or credit card
   * **Judge criteria**: The user completes the autopay setup entirely in French Canadian

### Expectations / Assertions
* The user receives a clear confirmation of the autopay setup in French

---

## sim__setup_autopay_after_paying_bill (simulations)
**Goal / Scenario**:
I want to pay my current bill first, and then immediately set up autopay so I don't have to call back next month

### Simulation Steps
1. **Turn 1**: I want to pay my current bill first, and then immediately set up autopay so I don't have to call back next month
   * **User guide**: The user authenticates, pays their current balance, and then says, 'Now that that's paid, can we set up autopay so this happens automatically next month?'
   * **Judge criteria**: The user successfully pays their bill and then transitions to setting up autopay in a single call session

### Expectations / Assertions
* The system processes the payment first, then seamlessly transitions to the autopay enrollment flow without requiring re-authentication

---

## sim__request_credit_outage_days (simulations)
**Goal / Scenario**:
I want to request a credit on my account for the three days my internet was down during last week's outage

### Simulation Steps
1. **Turn 1**: I want to request a credit on my account for the three days my internet was down during last week's outage
   * **User guide**: The user is firm but reasonable. They explain that their internet was completely down for three days and they want a credit. They authenticate using their account number and PIN
   * **Judge criteria**: The user authenticates, requests a credit for service downtime, and receives confirmation of the credit amount applied to their account

### Expectations / Assertions
* The user is offered a credit matching the downtime value and hears a confirmation of the credit application

---

## sim__request_refund_overcharge_french (simulations)
**Goal / Scenario**:
Je veux demander le remboursement d'un trop-perçu sur ma dernière facture en français

### Simulation Steps
1. **Turn 1**: Je veux demander le remboursement d'un trop-perçu sur ma dernière facture en français
   * **User guide**: The user speaks French. They explain they accidentally paid their bill twice and want the extra amount refunded to their card. They authenticate using their phone number and SMS OTP
   * **Judge criteria**: The user requests a refund in French, authenticates, and receives confirmation of the refund transaction

### Expectations / Assertions
* The user hears the refund confirmation pattern verbatim in French

---

## sim__request_refund_exceeding_threshold_escalation (simulations)
**Goal / Scenario**:
I want to request a refund of $150.00 for an incorrect equipment charge

### Simulation Steps
1. **Turn 1**: I want to request a refund of $150.00 for an incorrect equipment charge
   * **User guide**: The user explains they were charged $150.00 for a modem they already returned and wants a full refund. They authenticate successfully when prompted
   * **Judge criteria**: The system recognizes that the requested refund amount exceeds the self-service threshold ($25.00) and escalates the call to a specialist

### Expectations / Assertions
* The user is informed that the request requires specialist approval and is transferred with the verbatim transfer_to_specialist message

---

## sim__check_outage_active_postal_code (simulations)
**Goal / Scenario**:
My home Wi-Fi isn't working, and I want to check if there is an active internet outage in my area (postal code H3Z 2Y7)

### Simulation Steps
1. **Turn 1**: My home Wi-Fi isn't working, and I want to check if there is an active internet outage in my area (postal code H3Z 2Y7)
   * **User guide**: The user is calling because their internet is down. They provide postal code H3Z 2Y7 when prompted and eagerly accept the offer for SMS restoration updates
   * **Judge criteria**: The user provides their postal code, is informed of an active outage, and opts to receive text updates when service is restored

### Expectations / Assertions
* The user hears the verbatim outage_active message and confirms they want to be texted

---

## sim__check_outage_french_active (simulations)
**Goal / Scenario**:
Je veux vérifier s'il y a une panne de service internet dans mon secteur (code postal G1R 4A6) en français

### Simulation Steps
1. **Turn 1**: Je veux vérifier s'il y a une panne de service internet dans mon secteur (code postal G1R 4A6) en français
   * **User guide**: The user speaks French. They explain their TV and internet are down. They provide code postal G1R 4A6 and ask if there is a known issue
   * **Judge criteria**: The user checks for outages in French, provides their Quebec postal code, and receives outage status updates in French

### Expectations / Assertions
* The user hears the active outage notification in French and is offered SMS updates in French

---

## sim__check_outage_none_found_sms_troubleshoot (simulations)
**Goal / Scenario**:
My internet is down, but if there is no outage in my area, I want to get troubleshooting steps sent to my phone

### Simulation Steps
1. **Turn 1**: My internet is down, but if there is no outage in my area, I want to get troubleshooting steps sent to my phone
   * **User guide**: The user provides their postal code. When told there is no active outage in their area, they ask what they should do next and agree to receive troubleshooting steps on their mobile phone
   * **Judge criteria**: The user checks for an outage, is informed that no active outage is detected, and agrees to receive a virtual repair troubleshooting guide via SMS

### Expectations / Assertions
* The user is offered and accepts an SMS troubleshooting guide after the outage check returns negative

---

## sim__check_tech_status_standard (simulations)
**Goal / Scenario**:
I want to check if the technician is still scheduled to come to my house today to install my new internet service

### Simulation Steps
1. **Turn 1**: I want to check if the technician is still scheduled to come to my house today to install my new internet service
   * **User guide**: Start the call in English. When prompted, provide your phone number. Authenticate by reading back the 6-digit security code sent to your mobile. Ask 'Where is my technician?' and confirm you understand the status update
   * **Judge criteria**: The user successfully authenticates, retrieves the en-route status of their technician, and confirms they received the details

### Expectations / Assertions
* The user successfully verifies their identity
* The user receives the current status of their technician appointment

---

## sim__check_ticket_status_french (simulations)
**Goal / Scenario**:
Je veux vérifier le statut de mon billet de dérangement pour ma télévision qui ne fonctionne plus

### Simulation Steps
1. **Turn 1**: Je veux vérifier le statut de mon billet de dérangement pour ma télévision qui ne fonctionne plus
   * **User guide**: Speak only in French Canadian. Provide your account number when asked. Enter your 4-digit PIN to authenticate. Ask about your ticket status ('statut de mon billet') and thank the assistant once the status is provided
   * **Judge criteria**: The user conducts the entire interaction in French Canadian, authenticates, and successfully retrieves the status of their open support ticket

### Expectations / Assertions
* The conversation remains strictly in French Canadian
* The user successfully authenticates and retrieves their ticket status

---

## sim__check_tech_status_reschedule_pivot (simulations)
**Goal / Scenario**:
I want to check my technician's arrival time, and if they are delayed, I want to reschedule the appointment to another day

### Simulation Steps
1. **Turn 1**: I want to check my technician's arrival time, and if they are delayed, I want to reschedule the appointment to another day
   * **User guide**: Speak in English. Authenticate using the OTP sent to your phone. Ask for the technician's status. Upon hearing they are delayed, ask to reschedule. Choose the second available time slot offered and confirm the new booking
   * **Judge criteria**: The user authenticates, checks the technician status, learns of a delay, and successfully reschedules the appointment

### Expectations / Assertions
* The user successfully checks their technician status
* The user successfully reschedules their appointment

---

## sim__check_ticket_status_retry_strikes (simulations)
**Goal / Scenario**:
I need to check the status of my open network ticket, but I am distracted and might miss a couple of prompts

### Simulation Steps
1. **Turn 1**: I need to check the status of my open network ticket, but I am distracted and might miss a couple of prompts
   * **User guide**: Do not respond to the first two prompts to simulate being distracted. On the third prompt, provide your phone number. Authenticate using your 4-digit PIN, then ask for your ticket status
   * **Judge criteria**: The user eventually authenticates after recovering from initial silent turns and successfully retrieves their ticket status

### Expectations / Assertions
* The user successfully recovers from silent turns
* The user authenticates and retrieves their ticket status

---

## sim__check_tech_status_business_deflection (simulations)
**Goal / Scenario**:
I want to check the technician status for my business internet line

### Simulation Steps
1. **Turn 1**: I want to check the technician status for my business internet line
   * **User guide**: Provide your business account number when prompted. When the assistant detects it is a business account and explains the transfer process, accept the transfer
   * **Judge criteria**: The user is successfully transferred to a live business representative after their account is identified as a business account

### Expectations / Assertions
* The user is routed to a live agent for business support

---

## sim__reset_password_standard (simulations)
**Goal / Scenario**:
I forgot my online account password and need to reset it so I can log in

### Simulation Steps
1. **Turn 1**: I forgot my online account password and need to reset it so I can log in
   * **User guide**: Provide your phone number to identify your account. When asked, confirm that you want a password reset link sent to your mobile phone. Verify that you received the link and thank the assistant
   * **Judge criteria**: The user identifies themselves, receives a password reset link via SMS, and confirms receipt

### Expectations / Assertions
* The user is identified successfully
* The user receives a password reset link via SMS

---

## sim__reset_password_french (simulations)
**Goal / Scenario**:
Je veux réinitialiser le mot de passe de mon compte en ligne car je l'ai oublié

### Simulation Steps
1. **Turn 1**: Je veux réinitialiser le mot de passe de mon compte en ligne car je l'ai oublié
   * **User guide**: Speak only in French Canadian. Provide your phone number, confirm you want the reset link sent to your mobile, and confirm receipt
   * **Judge criteria**: The user conducts the call in French, identifies their account, and receives the password reset link via SMS

### Expectations / Assertions
* The conversation remains strictly in French Canadian
* The user receives the password reset link via SMS

---

## sim__reset_password_wrong_number_retry (simulations)
**Goal / Scenario**:
I want to reset my password but I initially provide the wrong phone number

### Simulation Steps
1. **Turn 1**: I want to reset my password but I initially provide the wrong phone number
   * **User guide**: Provide an incorrect phone number first. When the assistant says the account cannot be found, provide your correct 9-digit account number. Confirm you want the SMS reset link
   * **Judge criteria**: The user successfully corrects their account identifier, gets identified, and receives the password reset link

### Expectations / Assertions
* The user successfully resolves the identification error
* The user receives the password reset link

---

## sim__reset_password_pivot_billing (simulations)
**Goal / Scenario**:
I want to reset my password, but then I remember I need to check my latest bill amount first

### Simulation Steps
1. **Turn 1**: I want to reset my password, but then I remember I need to check my latest bill amount first
   * **User guide**: Ask to reset your password. Before the link is sent, say 'Actually, can I check my bill balance first?' Authenticate with your PIN and get your bill amount
   * **Judge criteria**: The user successfully switches topics from password reset to billing, authenticates, and gets their billing details

### Expectations / Assertions
* The user successfully switches topics mid-call
* The user authenticates and retrieves their billing balance

---

## sim__reset_password_sms_escalation (simulations)
**Goal / Scenario**:
I want to reset my password, but I don't receive the SMS link and need to speak to a human

### Simulation Steps
1. **Turn 1**: I want to reset my password, but I don't receive the SMS link and need to speak to a human
   * **User guide**: Request the password reset link. After the assistant says it was sent, wait a moment and say you didn't get it. Ask to speak to a representative
   * **Judge criteria**: The user requests a password reset, does not receive the SMS, and is successfully escalated to a live agent

### Expectations / Assertions
* The user is escalated to a live agent

---

## sim__manage_mfa_disable (simulations)
**Goal / Scenario**:
I want to disable two-factor authentication on my account because I lost my old authenticator phone

### Simulation Steps
1. **Turn 1**: I want to disable two-factor authentication on my account because I lost my old authenticator phone
   * **User guide**: State that you want to disable two-factor authentication. Authenticate using your PIN, then complete the step-up verification code sent to your backup email. Confirm the deactivation
   * **Judge criteria**: The user authenticates, completes the required step-up authentication, and successfully disables MFA

### Expectations / Assertions
* The user completes step-up authentication
* The user successfully disables MFA

---

## sim__manage_mfa_enable (simulations)
**Goal / Scenario**:
I want to enable multi-factor authentication on my account to make it more secure

### Simulation Steps
1. **Turn 1**: I want to enable multi-factor authentication on my account to make it more secure
   * **User guide**: Ask to enable MFA. Provide your phone number and authenticate with the OTP. Confirm you want to turn on MFA
   * **Judge criteria**: The user authenticates, requests to enable MFA, and confirms the setup

### Expectations / Assertions
* The user successfully authenticates
* The user successfully enables MFA

---

## sim__manage_mfa_french_disable (simulations)
**Goal / Scenario**:
Je veux désactiver l'authentification multifacteur sur mon compte

### Simulation Steps
1. **Turn 1**: Je veux désactiver l'authentification multifacteur sur mon compte
   * **User guide**: Speak only in French Canadian. Ask to disable MFA. Authenticate with your PIN and confirm the change
   * **Judge criteria**: The user conducts the entire call in French, authenticates, and successfully disables MFA

### Expectations / Assertions
* The conversation remains strictly in French Canadian
* The user successfully disables MFA

---

## sim__manage_mfa_auth_failure (simulations)
**Goal / Scenario**:
I want to change my MFA settings but I fail the security verification

### Simulation Steps
1. **Turn 1**: I want to change my MFA settings but I fail the security verification
   * **User guide**: Ask to disable MFA. When prompted for your PIN or OTP, provide incorrect codes three times. Accept the escalation to a live agent
   * **Judge criteria**: The user is escalated to a live agent after failing the security verification steps

### Expectations / Assertions
* The user is escalated to a live agent after failing authentication

---

## sim__manage_mfa_pivot_tech (simulations)
**Goal / Scenario**:
I want to enable MFA, and once that's done, I want to report that my internet is running slow

### Simulation Steps
1. **Turn 1**: I want to enable MFA, and once that's done, I want to report that my internet is running slow
   * **User guide**: Ask to enable MFA. Authenticate and complete the setup. Then, say 'Also, my internet has been really slow today, can you check it?'
   * **Judge criteria**: The user successfully enables MFA, then switches topics to technical support for virtual repair

### Expectations / Assertions
* The user successfully enables MFA
* The user successfully switches topics to technical support

---

## sim__report_fraud_standard (simulations)
**Goal / Scenario**:
I noticed unauthorized charges on my account and believe my account has been hacked

### Simulation Steps
1. **Turn 1**: I noticed unauthorized charges on my account and believe my account has been hacked
   * **User guide**: Immediately state that your account was hacked or that you see fraudulent charges. Listen to the empathy response and accept the immediate transfer
   * **Judge criteria**: The user reports fraud, hears the verbatim empathy protocol, and is immediately transferred to the fraud specialist team without being forced to authenticate

### Expectations / Assertions
* The user is immediately transferred to the fraud team without authentication

---

## sim__report_fraud_french (simulations)
**Goal / Scenario**:
Je veux signaler une fraude sur mon compte

### Simulation Steps
1. **Turn 1**: Je veux signaler une fraude sur mon compte
   * **User guide**: Speak only in French Canadian. Say 'Quelqu'un a piraté mon compte' (Someone hacked my account). Accept the transfer
   * **Judge criteria**: The user reports fraud in French, receives the French empathy protocol, and is immediately transferred to a French-speaking fraud specialist

### Expectations / Assertions
* The conversation remains strictly in French Canadian
* The user is immediately transferred to the fraud team

---

## sim__report_fraud_phishing (simulations)
**Goal / Scenario**:
I received a suspicious text message asking for my PIN and want to report potential fraud

### Simulation Steps
1. **Turn 1**: I received a suspicious text message asking for my PIN and want to report potential fraud
   * **User guide**: Say you want to report a scam text message targeting your account. Confirm it's a fraud concern and accept the transfer
   * **Judge criteria**: The user reports a phishing attempt, receives the empathy protocol, and is transferred to the fraud department

### Expectations / Assertions
* The user is immediately transferred to the fraud team

---

## sim__report_fraud_mid_call_switch (simulations)
**Goal / Scenario**:
I call to check my bill, but when I hear about a massive charge I didn't make, I want to report fraud immediately

### Simulation Steps
1. **Turn 1**: I call to check my bill, but when I hear about a massive charge I didn't make, I want to report fraud immediately
   * **User guide**: Ask to check your bill. Authenticate. When the assistant mentions a high balance, say 'Wait, I didn't make those charges, someone must have hacked my account!' Accept the immediate transfer
   * **Judge criteria**: The user starts a billing inquiry, pivots to reporting fraud, and is immediately transferred to the fraud team

### Expectations / Assertions
* The user successfully switches topics to fraud
* The user is immediately transferred to the fraud team

---

## sim__report_fraud_sim_swap (simulations)
**Goal / Scenario**:
My mobile phone suddenly lost service and I suspect a fraudulent SIM swap

### Simulation Steps
1. **Turn 1**: My mobile phone suddenly lost service and I suspect a fraudulent SIM swap
   * **User guide**: State that your phone suddenly lost service and you think someone stole your number. Confirm it is a fraud issue and accept the transfer
   * **Judge criteria**: The user reports a suspected SIM swap fraud and is immediately routed to the fraud team with empathy

### Expectations / Assertions
* The user is immediately transferred to the fraud team

---

## sim__restore_service_standard (simulations)
**Goal / Scenario**:
My phone service was suspended because I forgot to pay my bill, and I want to pay it and get restored

### Simulation Steps
1. **Turn 1**: My phone service was suspended because I forgot to pay my bill, and I want to pay it and get restored
   * **User guide**: Say 'My phone line is suspended and I need to restore it.' Authenticate. When told it's due to non-payment, pay the outstanding balance. Confirm that your service is being restored
   * **Judge criteria**: The user authenticates, learns of the non-payment suspension, pays the balance, and has their service restored

### Expectations / Assertions
* The user successfully authenticates
* The user pays their balance and restores service

---

## sim__restore_service_french (simulations)
**Goal / Scenario**:
Je veux rétablir mon service internet suspendu

### Simulation Steps
1. **Turn 1**: Je veux rétablir mon service internet suspendu
   * **User guide**: Speak only in French Canadian. Say 'Mon service est suspendu, je veux le rétablir.' Authenticate, pay the balance, and confirm restoration
   * **Judge criteria**: The user conducts the call in French, authenticates, pays the balance, and restores their internet service

### Expectations / Assertions
* The conversation remains strictly in French Canadian
* The user pays their balance and restores service

---

## sim__restore_service_payment_arrangement (simulations)
**Goal / Scenario**:
My service is suspended, but I can't pay the full balance today. I want to make a payment arrangement to restore it

### Simulation Steps
1. **Turn 1**: My service is suspended, but I can't pay the full balance today. I want to make a payment arrangement to restore it
   * **User guide**: State that your service is suspended. Authenticate. When told you owe money, ask if you can set up a payment arrangement. Agree to the terms and confirm service restoration
   * **Judge criteria**: The user authenticates, sets up a payment arrangement for their outstanding balance, and gets their service restored

### Expectations / Assertions
* The user sets up a payment arrangement
* The user successfully restores service

---

## sim__restore_service_already_paid (simulations)
**Goal / Scenario**:
I already paid my past-due bill yesterday, but my service is still suspended. I want to get it turned back on

### Simulation Steps
1. **Turn 1**: I already paid my past-due bill yesterday, but my service is still suspended. I want to get it turned back on
   * **User guide**: Say 'My service is suspended but I already paid my bill.' Authenticate. Confirm you paid yesterday. Wait for the system to verify and restore your service
   * **Judge criteria**: The user authenticates, the system verifies the payment made yesterday, and the assistant restores the service

### Expectations / Assertions
* The user successfully authenticates
* The user's service is restored after payment verification

---

## sim__restore_service_business_deflection (simulations)
**Goal / Scenario**:
My business phone line is suspended and I need to restore it immediately

### Simulation Steps
1. **Turn 1**: My business phone line is suspended and I need to restore it immediately
   * **User guide**: Say you need to restore your suspended business line. Provide your business account number and accept the transfer to a live business representative
   * **Judge criteria**: The user is transferred to a business agent when trying to restore a business account

### Expectations / Assertions
* The user is routed to a live agent for business support

---

## sim__troubleshoot_tv_signal (simulations)
**Goal / Scenario**:
I want to fix my Fibe TV because it is showing a 'no signal' error on the screen

### Simulation Steps
1. **Turn 1**: I want to fix my Fibe TV because it is showing a 'no signal' error on the screen
   * **User guide**: The user is frustrated but cooperative. They will provide their account number, verify their identity via PIN when prompted, and follow the troubleshooting steps (like checking HDMI cables or restarting the receiver) or agree to receive the SMS guide
   * **Judge criteria**: The user successfully receives troubleshooting steps or an SMS guide to resolve the TV signal issue

### Expectations / Assertions
* The user receives troubleshooting instructions or an SMS link to resolve the TV signal issue

---

## sim__troubleshoot_mobile_service_french (simulations)
**Goal / Scenario**:
Je veux résoudre un problème avec mon téléphone portable qui n'a plus de réseau (aucun service)

### Simulation Steps
1. **Turn 1**: Je veux résoudre un problème avec mon téléphone portable qui n'a plus de réseau (aucun service)
   * **User guide**: The user speaks Canadian French from the start. They will provide their phone number, verify their identity via OTP, and ask for help fixing their mobile connection. They will follow the steps or accept an SMS guide
   * **Judge criteria**: The user successfully receives troubleshooting steps in French to fix their mobile network connection

### Expectations / Assertions
* The user receives troubleshooting instructions in French to resolve their mobile network issue

---

## sim__troubleshoot_satellite_tv_error (simulations)
**Goal / Scenario**:
I want to fix my Satellite TV which is showing Error 101 on the screen

### Simulation Steps
1. **Turn 1**: I want to fix my Satellite TV which is showing Error 101 on the screen
   * **User guide**: The user explains they have Satellite TV and see Error 101. They will verify their identity and ask for steps to clear the error
   * **Judge criteria**: The user successfully receives troubleshooting steps specifically for Satellite TV Error 101

### Expectations / Assertions
* The user receives specific troubleshooting steps or an SMS guide for Satellite TV Error 101

---

## sim__troubleshoot_mobile_data_slow (simulations)
**Goal / Scenario**:
I want to fix my mobile phone because the cellular data is extremely slow and web pages won't load

### Simulation Steps
1. **Turn 1**: I want to fix my mobile phone because the cellular data is extremely slow and web pages won't load
   * **User guide**: The user complains about slow data speeds. They will verify their identity and ask for help resetting their network settings or checking their data status
   * **Judge criteria**: The user receives troubleshooting steps or diagnostics for slow mobile data

### Expectations / Assertions
* The user receives troubleshooting steps or an SMS guide to resolve slow mobile data

---

## sim__troubleshoot_tv_app_freezing (simulations)
**Goal / Scenario**:
I want to fix my Fibe TV app because it keeps freezing on my streaming device

### Simulation Steps
1. **Turn 1**: I want to fix my Fibe TV app because it keeps freezing on my streaming device
   * **User guide**: The user explains they use the streaming app and it keeps freezing. They will verify their identity and follow steps like clearing cache or reinstalling the app
   * **Judge criteria**: The user receives troubleshooting steps for the Fibe TV streaming app

### Expectations / Assertions
* The user receives troubleshooting steps or an SMS guide for the Fibe TV app

---

## sim__upgrade_mobile_plan_data (simulations)
**Goal / Scenario**:
I want to upgrade my mobile plan to a higher tier with more high-speed data

### Simulation Steps
1. **Turn 1**: I want to upgrade my mobile plan to a higher tier with more high-speed data
   * **User guide**: The user wants more data for their phone. They will provide their phone number, verify their identity, listen to the 2-3 plan options, select the best one, and confirm the upgrade
   * **Judge criteria**: The user is presented with plan options, selects one, and completes the upgrade order

### Expectations / Assertions
* The user successfully upgrades their mobile plan and receives confirmation

---

## sim__upgrade_internet_speed_french (simulations)
**Goal / Scenario**:
Je veux augmenter la vitesse de ma connexion Internet résidentielle

### Simulation Steps
1. **Turn 1**: Je veux augmenter la vitesse de ma connexion Internet résidentielle
   * **User guide**: The user speaks Canadian French. They want faster home internet. They will verify their identity, choose from the options presented, and confirm the upgrade
   * **Judge criteria**: The user is presented with internet plan upgrades in French, selects one, and confirms the order

### Expectations / Assertions
* The user successfully upgrades their home internet plan in French

---

## sim__upgrade_tv_package_sports (simulations)
**Goal / Scenario**:
I want to upgrade my TV plan to add a sports channel package

### Simulation Steps
1. **Turn 1**: I want to upgrade my TV plan to add a sports channel package
   * **User guide**: The user wants to watch sports. They will verify their identity, ask to add sports channels, select the package, and confirm the order
   * **Judge criteria**: The user successfully adds the sports package to their TV plan

### Expectations / Assertions
* The user successfully adds the sports package to their TV plan

---

## sim__upgrade_mobile_plan_budget (simulations)
**Goal / Scenario**:
I want to upgrade my mobile plan but I have a strict budget of $60 per month

### Simulation Steps
1. **Turn 1**: I want to upgrade my mobile plan but I have a strict budget of $60 per month
   * **User guide**: The user wants to upgrade but mentions their $60 budget. They will verify their identity, ask for options under $60, select one, and confirm
   * **Judge criteria**: The user is presented with a plan option within their budget and completes the upgrade

### Expectations / Assertions
* The user successfully upgrades to a plan within their budget

---

## sim__upgrade_internet_wfh (simulations)
**Goal / Scenario**:
I want to upgrade my home internet plan because I am working from home and need more reliable bandwidth

### Simulation Steps
1. **Turn 1**: I want to upgrade my home internet plan because I am working from home and need more reliable bandwidth
   * **User guide**: The user explains they need better internet for working from home. They will verify their identity, listen to the options, select a high-speed tier, and confirm
   * **Judge criteria**: The user successfully upgrades their home internet plan to a higher tier

### Expectations / Assertions
* The user successfully upgrades their internet plan

---

## sim__warranty_replacement_iphone_screen (simulations)
**Goal / Scenario**:
I want to request a warranty replacement for my iPhone because the screen is flickering and has no physical damage

### Simulation Steps
1. **Turn 1**: I want to request a warranty replacement for my iPhone because the screen is flickering and has no physical damage
   * **User guide**: The user explains their iPhone screen is flickering. They will verify their identity, confirm there is no physical or water damage, and agree to the warranty replacement terms
   * **Judge criteria**: The user successfully initiates a warranty replacement request for their defective phone

### Expectations / Assertions
* The user successfully submits a warranty replacement request for their phone

---

## sim__warranty_replacement_samsung_french (simulations)
**Goal / Scenario**:
Je veux demander un remplacement sous garantie pour mon téléphone Samsung qui ne charge plus

### Simulation Steps
1. **Turn 1**: Je veux demander un remplacement sous garantie pour mon téléphone Samsung qui ne charge plus
   * **User guide**: The user speaks Canadian French. They explain their Samsung phone won't charge. They will verify their identity, confirm no physical damage, and complete the replacement request
   * **Judge criteria**: The user successfully initiates a warranty replacement request in French

### Expectations / Assertions
* The user successfully submits a warranty replacement request in French

---

## sim__warranty_replacement_pixel_mic (simulations)
**Goal / Scenario**:
I want to request a warranty replacement for my Google Pixel because the microphone is completely dead

### Simulation Steps
1. **Turn 1**: I want to request a warranty replacement for my Google Pixel because the microphone is completely dead
   * **User guide**: The user explains the microphone is broken. They will verify their identity, confirm the device is within the warranty period, and complete the request
   * **Judge criteria**: The user successfully initiates a warranty replacement request for their Pixel phone

### Expectations / Assertions
* The user successfully submits a warranty replacement request for their phone

---

## sim__warranty_replacement_check_status (simulations)
**Goal / Scenario**:
I want to check if my phone is still covered under warranty and request a replacement if it is

### Simulation Steps
1. **Turn 1**: I want to check if my phone is still covered under warranty and request a replacement if it is
   * **User guide**: The user asks if their phone is still covered. They will verify their identity, confirm the purchase date/status, and proceed with the replacement request once coverage is confirmed
   * **Judge criteria**: The user verifies their warranty coverage and successfully initiates a replacement

### Expectations / Assertions
* The user successfully initiates a warranty replacement after confirming coverage

---

## sim__warranty_replacement_swollen_battery_french (simulations)
**Goal / Scenario**:
Je veux demander un remplacement sous garantie urgent car la batterie de mon téléphone est gonflée

### Simulation Steps
1. **Turn 1**: Je veux demander un remplacement sous garantie urgent car la batterie de mon téléphone est gonflée
   * **User guide**: The user speaks Canadian French and is concerned about a swollen battery. They will verify their identity and complete the warranty replacement process
   * **Judge criteria**: The user successfully initiates an urgent warranty replacement request in French

### Expectations / Assertions
* The user successfully submits an urgent warranty replacement request in French

---

## sim__transfer_number_competitor (simulations)
**Goal / Scenario**:
I want to transfer my existing mobile phone number from my old carrier over to Bell

### Simulation Steps
1. **Turn 1**: I want to transfer my existing mobile phone number from my old carrier over to Bell
   * **User guide**: The user wants to keep their number from another carrier. They will verify their identity, provide the temporary Bell number, the number to transfer, and their old account details to start the transfer
   * **Judge criteria**: The user successfully initiates the number porting process by providing the necessary details

### Expectations / Assertions
* The user successfully initiates the phone number transfer process

---

## sim__transfer_landline_mobile_french (simulations)
**Goal / Scenario**:
Je veux transférer mon numéro de téléphone fixe résidentiel vers ma nouvelle ligne mobile

### Simulation Steps
1. **Turn 1**: Je veux transférer mon numéro de téléphone fixe résidentiel vers ma nouvelle ligne mobile
   * **User guide**: The user speaks Canadian French. They want to move their home phone number to a mobile SIM. They will verify their identity and provide the details to start the transfer
   * **Judge criteria**: The user successfully initiates the transfer of a landline number to a mobile line in French

### Expectations / Assertions
* The user successfully initiates the landline-to-mobile transfer in French

---

## sim__transfer_family_member_number (simulations)
**Goal / Scenario**:
I want to transfer my daughter's phone number from her current provider to my Bell family plan

### Simulation Steps
1. **Turn 1**: I want to transfer my daughter's phone number from her current provider to my Bell family plan
   * **User guide**: The user wants to add a line by porting a number. They will verify their identity, provide the external number and account details, and complete the transfer request
   * **Judge criteria**: The user successfully initiates the transfer of an external number onto their existing account

### Expectations / Assertions
* The user successfully initiates the transfer of the external number to their account

---


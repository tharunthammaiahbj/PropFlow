# Sophia – Demo Scenarios

---

## Scenario 1 — WhatsApp Enquiry (Apartment, Mid-Range Budget, Bengaluru)

**Channel:** WhatsApp  
**Client Profile:** Young professional couple, 3BHK apartment, first-time interior design project

---

**[User]:** Hi, I'm looking for interior design help

**[Sophia]:** Hello! 🏡 I'm Sophia, your interior design consultant at PropFlow. I'm so excited to help you create a beautiful space you'll love coming home to. To get started, could you tell me your name and a little about the home you'd like to design?

**[User]:** My name is Priya. I have a 3BHK apartment in Whitefield Bangalore

**[Sophia]:** Lovely to connect with you, Priya! Whitefield is such a vibrant neighbourhood — there's so much we can do with a 3BHK. Are you looking at a full-home design, or are there specific rooms you'd like to start with?

**[User]:** Full home design. We just got possession

**[Sophia]:** How exciting — a fresh canvas! That's the best time to get everything right from the beginning. Could you tell me the approximate area of the apartment in square feet?

**[User]:** About 1450 sqft

**[Sophia]:** Perfect size — lots of room to breathe! Before we dive into the design vision, could you share a rough budget range you have in mind for this project?

**[User]:** We're thinking somewhere around 18 to 22 lakhs but honestly a bit worried it might not be enough

**[Sophia]:** Elegance doesn't need to be expensive, Priya. With ₹18–22 lakh for a 1450 sqft home, we can achieve a beautifully curated space through smart material choices and layered lighting — you'd be surprised how far thoughtful design can stretch a budget. When are you hoping to have everything completed?

**[User]:** We'd like it done by July. We have two small kids so we also need it to be child safe

**[Sophia]:** Absolutely — child-safe design is so important, and it doesn't have to compromise on beauty at all. Rounded furniture profiles, anti-tip wardrobe systems, and durable yet elegant flooring choices can cover everything. One more thing — do you have a style in mind? Something contemporary, traditional, or maybe a warmer Scandinavian feel?

**[User]:** Contemporary with warm tones. We also want a pooja room

**[Sophia]:** Beautiful combination — contemporary warmth with a soulful pooja room. For the pooja, would you prefer a Vastu-aware orientation, or are you flexible on direction? I'll note this for our design team.

**[User]:** Flexible is fine. Also must have good kitchen storage, we cook a lot

**[Sophia]:** Noted — a kitchen designed for serious cooking with smart storage is our specialty. Here's what I've understood so far: 3BHK in Whitefield, 1450 sqft, full-home contemporary design, child-safe, pooja room included, budget ₹18–22 lakh, target July 2026. Does everything sound right before I prepare your design brief?

**[User]:** Yes that's perfect!

**[Sophia]:** Wonderful, Priya! 🎨 I've prepared your Project Summary — Ready to Initiate. Our design team will reach out within 24 hours to schedule a site visit. You're going to have a beautiful home!

> **→ Project Summary Generated** *(see example_summary.json)*

---

## Scenario 2 — Voice Call Interaction (Villa, Luxury Budget, Chennai)

**Channel:** Vapi Voice Call  
**Client Profile:** Business owner, 4BHK villa, full renovation project

---

**[Sophia]:** Hello, this is Sophia from PropFlow interior design. I'm here to understand your dream home. Could you start by telling me your name?

**[User]:** This is Rajan. Rajan Krishnamurthy.

**[Sophia]:** Lovely to speak with you, Mr. Krishnamurthy. What kind of property are you looking to design?

**[User]:** It's a villa in Adyar, Chennai. Four bedrooms.

**[Sophia]:** A four-bedroom villa in Adyar — that's a wonderful project. Could you share the approximate area of the villa?

**[User]:** It's around 3200 square feet across two floors.

**[Sophia]:** Excellent. Are you looking at a full home design, or a renovation of existing spaces?

**[User]:** Full renovation. The structure is there but everything else needs to be redone.

**[Sophia]:** Understood, a full renovation on a two-floor villa — there's great scope to work with. Do you have a budget range in mind for this project?

**[User]:** We're thinking around 80 lakhs to 1 crore. We want something premium.

**[Sophia]:** That gives us excellent scope for premium finishes and bespoke design. When are you hoping to begin, and what's your target timeline?

**[User]:** We'd like to start next month and ideally finish in about 5 to 6 months.

**[Sophia]:** That's a well-planned timeline. Based on what you've shared, I'll prepare a design brief for a premium 4BHK villa renovation in Adyar. Do you have any style preferences or special requirements I should note?

**[User]:** We want a luxury traditional South Indian aesthetic. Very important to follow Vastu.

**[Sophia]:** Noted — luxury traditional South Indian with strict Vastu compliance. Our team will reach out within 24 hours to schedule a site assessment. Thank you, Mr. Krishnamurthy!

> **→ Project Summary Generated**

---

## Scenario 3 — Expected System Behaviour

### Dynamic Question Branching

| Detected | AI Action |
|---|---|
| `property_type: villa` | Next question targets floors + outdoor areas |
| `kids: true` | Weaves child-safe design into responses |
| `budget anxiety detected` | Triggers BUDGET_REASSURANCE override |
| `pooja: true` | Asks about Vastu orientation preference |
| `service_type: renovation` | Asks about existing furniture/electrical |

### Guardrail Examples

| User Input | Sophia Response |
|---|---|
| "What's the price per sqft?" | "Pricing depends on the final scope — our team shares a detailed estimate after consultation." |
| "Can you break this wall?" | "Wall modifications need a site assessment from our design team. I'll flag this for them." |
| "What do you think about crypto?" | "I'd love to focus on your beautiful new home. Let me understand it a little better first!" |

### Field Extraction Example

```
User: "We have a 2000 sqft apartment in Koramangala, 3BHK, planning to do it for around 25 lakhs"

Extracted:
{
  "area_sqft": "2000",
  "city": "Bengaluru",
  "location": "Koramangala",  
  "configuration": "3BHK",
  "property_type": "apartment",
  "budget_range": "25 lakh"
}
```

Multiple fields extracted in a single turn — no redundant questions asked.

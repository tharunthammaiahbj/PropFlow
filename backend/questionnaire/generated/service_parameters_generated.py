"""AUTO-GENERATED from quest-characters service-parameters.ts — do not hand-edit."""
from __future__ import annotations
from typing import TypedDict, List

class ParamDef(TypedDict):
    id: str
    label: str
    hint: str

class ServiceParamSet(TypedDict):
    required: List[ParamDef]
    optional: List[ParamDef]

SERVICE_PARAMS: dict[str, ServiceParamSet] = {
  "residential_interiors": {
    "required": [
      {
        "id": "project_type",
        "label": "Type of home (residential interiors)",
        "hint": "flat/apartment, villa, independent house, penthouse"
      },
      {
        "id": "rooms",
        "label": "BHK / room count (residential)",
        "hint": "2BHK, 3BHK, 4BHK, specific rooms to design"
      },
      {
        "id": "size_sqft",
        "label": "Carpet area for interior (sqft)",
        "hint": "actual or approx carpet area in sqft"
      },
      {
        "id": "style",
        "label": "Interior style preference",
        "hint": "modern, traditional, minimal, japandi, contemporary, neo-indian, eclectic"
      },
      {
        "id": "budget",
        "label": "Interior design + execution budget",
        "hint": "total in lakhs/INR for design and execution"
      },
      {
        "id": "financing",
        "label": "Financing preference",
        "hint": "upfront, EMI, loan – how you plan to pay"
      },
      {
        "id": "timeline",
        "label": "When interior work to be completed",
        "hint": "days, weeks, or months to completion"
      },
      {
        "id": "preferred_start",
        "label": "When you want interior work to start",
        "hint": "ASAP, next month, after monsoon, etc."
      },
      {
        "id": "location",
        "label": "Project location (city/area)",
        "hint": "city and area where the interior work is"
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone call, WhatsApp, or email"
      },
      
    ],
    "optional": [
      {
        "id": "must_haves",
        "label": "Must-haves for this interior",
        "hint": "wardrobes, false ceiling, specific materials, colors"
      },
      {
        "id": "avoid",
        "label": "What to avoid in this interior",
        "hint": "materials, colors, or elements they don’t want"
      },
      {
        "id": "site_ready",
        "label": "Is the site ready for interior work",
        "hint": "yes/no – possession, demolition done"
      },
      {
        "id": "storage_needs",
        "label": "Storage requirements",
        "hint": "wardrobes, lofts, modular storage, shoe rack"
      },
      {
        "id": "lighting_pref",
        "label": "Lighting preference",
        "hint": "warm white, cool white, natural, dimmable"
      },
      {
        "id": "notes",
        "label": "Special focus (residential interior)",
        "hint": "kids room, pooja room, home office, pet-friendly"
      },
      {
        "id": "moodboard_refs",
        "label": "Inspiration / moodboard",
        "hint": "Pinterest links, reference images, mood"
      },
      {
        "id": "special_zones",
        "label": "Priority zones",
        "hint": "living room, master bedroom, kitchen, balcony"
      },
      {
        "id": "material_preference",
        "label": "Material preference (interior)",
        "hint": "wood, laminate, veneer, tiles, marble"
      }
    ]
  },
  "residential_construction": {
    "required": [
      {
        "id": "project_type",
        "label": "Type of construction (residential)",
        "hint": "villa, independent house, duplex, row house"
      },
      {
        "id": "plot_size_sqft",
        "label": "Plot size or built-up area (sqft)",
        "hint": "plot area and/or built-up in sqft"
      },
      {
        "id": "floors",
        "label": "Number of floors (G+?)",
        "hint": "G+1, G+2, G+3, etc."
      },
      {
        "id": "has_soil_test",
        "label": "Soil test completed for plot",
        "hint": "yes/no – soil test done for foundation"
      },
      {
        "id": "has_approvals",
        "label": "Building plan / sanctions",
        "hint": "yes/no – sanctioned plan or approval status"
      },
      {
        "id": "budget",
        "label": "Full construction budget",
        "hint": "total in lakhs/INR for complete build"
      },
      {
        "id": "financing",
        "label": "Financing preference",
        "hint": "upfront, EMI, loan – how you plan to pay"
      },
      {
        "id": "timeline",
        "label": "Construction completion timeline",
        "hint": "target months to complete build"
      },
      {
        "id": "preferred_start",
        "label": "When to start construction",
        "hint": "ASAP, after rains, next quarter"
      },
      {
        "id": "location",
        "label": "Site location (city/area)",
        "hint": "city and area where the work is"
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone, WhatsApp, or email"
      },
      
    ],
    "optional": [
      {
        "id": "material_grade",
        "label": "Construction material grade",
        "hint": "standard, premium, luxury – finish level"
      },
      {
        "id": "foundation_type",
        "label": "Foundation type",
        "hint": "isolated, combined, raft – if known"
      },
      {
        "id": "sustainability",
        "label": "Green / sustainability needs",
        "hint": "rainwater harvesting, solar-ready, eco materials"
      },
      {
        "id": "notes",
        "label": "Other construction requirements",
        "hint": "Vastu, specific room sizes, etc."
      },
      {
        "id": "power_water_avail",
        "label": "Power and water at site",
        "hint": "electricity connection, water source availability"
      },
      {
        "id": "contractor_pref",
        "label": "Contractor / execution preference",
        "hint": "self, contractor, turnkey"
      },
      {
        "id": "other_construction",
        "label": "Any other construction detail",
        "hint": "boundary, compound, etc."
      }
    ]
  },
  "commercial_interiors": {
    "required": [
      {
        "id": "project_type",
        "label": "Type of commercial space",
        "hint": "office, retail, restaurant, clinic, salon, showroom, coworking"
      },
      {
        "id": "space_use",
        "label": "Primary use of the space",
        "hint": "workplace, retail, F&B, healthcare, hospitality"
      },
      {
        "id": "size_sqft",
        "label": "Carpet area for fit-out (sqft)",
        "hint": "usable interior area in sqft"
      },
      {
        "id": "brand_theme",
        "label": "Brand or visual theme",
        "hint": "brand guidelines, colors, logo usage, vibe"
      },
      {
        "id": "occupancy",
        "label": "Occupancy / headcount",
        "hint": "number of employees, seats, or visitors"
      },
      {
        "id": "budget",
        "label": "Commercial fit-out budget",
        "hint": "total in lakhs/INR for interior fit-out"
      },
      {
        "id": "timeline",
        "label": "Fit-out / move-in timeline",
        "hint": "target completion or move-in date"
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone, WhatsApp, or email"
      },
      
    ],
    "optional": [
      {
        "id": "must_haves",
        "label": "Must-haves for fit-out",
        "hint": "meeting rooms, pantry, reception, cabin count"
      },
      {
        "id": "avoid",
        "label": "What to avoid in fit-out",
        "hint": "materials, styles, or elements"
      },
      {
        "id": "furniture_need",
        "label": "Furniture in scope",
        "hint": "included in fit-out or client providing"
      },
      {
        "id": "av_need",
        "label": "AV and tech in scope",
        "hint": "screens, video conferencing, sound, WiFi"
      },
      {
        "id": "notes",
        "label": "Other commercial requirements",
        "hint": "shift timings, security, access"
      },
      {
        "id": "preferred_start",
        "label": "When fit-out should start",
        "hint": "ASAP, after tenant, next month"
      },
      {
        "id": "compliance",
        "label": "Compliance requirements",
        "hint": "fire safety, accessibility, local norms"
      },
      {
        "id": "special_zones",
        "label": "Key zones (commercial)",
        "hint": "reception, cabins, breakout, server room"
      },
      {
        "id": "other_commercial",
        "label": "Any other commercial detail",
        "hint": "signage, branding, etc."
      }
    ]
  },
  "commercial_construction": {
    "required": [
      {
        "id": "project_type",
        "label": "Type of commercial building",
        "hint": "office building, warehouse, retail, mixed-use, factory shed"
      },
      {
        "id": "construction_type",
        "label": "Construction type",
        "hint": "new build, extension, shell & core, RCC frame"
      },
      {
        "id": "size_sqft",
        "label": "Built-up area (sqft)",
        "hint": "total built-up or plinth area in sqft"
      },
      {
        "id": "delivery_phase",
        "label": "Scope of delivery",
        "hint": "design only, structure only, MEP, turnkey"
      },
      {
        "id": "contract_type",
        "label": "Contract type preferred",
        "hint": "lump sum, item rate, design-build, EPC"
      },
      {
        "id": "budget",
        "label": "Commercial construction budget",
        "hint": "total in lakhs/INR for structure/build"
      },
      {
        "id": "timeline",
        "label": "Build / handover timeline",
        "hint": "target completion or phase handover"
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone, WhatsApp, or email"
      },
      
    ],
    "optional": [
      {
        "id": "mep_scope",
        "label": "MEP in scope",
        "hint": "electrical, plumbing, HVAC, fire fighting – what’s in scope"
      },
      {
        "id": "compliance_focus",
        "label": "Compliance / codes",
        "hint": "local building norms, green rating, fire NOC"
      },
      {
        "id": "notes",
        "label": "Other build requirements",
        "hint": "loading docks, ceiling height, etc."
      },
      {
        "id": "preferred_start",
        "label": "When construction to start",
        "hint": "ASAP, next quarter, after approval"
      },
      {
        "id": "must_haves",
        "label": "Must-haves for build",
        "hint": "crane, basement, specific finishes"
      },
      {
        "id": "avoid",
        "label": "What to avoid",
        "hint": "materials, methods, or constraints"
      },
      {
        "id": "site_conditions",
        "label": "Site conditions",
        "hint": "soil, water table, access, existing structures"
      },
      {
        "id": "vendor_pref",
        "label": "Vendor / contractor preference",
        "hint": "if any preferred or blacklisted"
      },
      {
        "id": "other_construction_com",
        "label": "Any other commercial build detail",
        "hint": ""
      }
    ]
  },
  "property_development": {
    "required": [
      {
        "id": "project_type",
        "label": "Type of development",
        "hint": "residential project, commercial, mixed-use, plotted, villa layout"
      },
      {
        "id": "development_phase",
        "label": "Current development phase",
        "hint": "planning, design, execution, delivery"
      },
      {
        "id": "size_sqft",
        "label": "Project scale (sqft)",
        "hint": "total land/ built-up or per unit in sqft"
      },
      {
        "id": "num_units",
        "label": "Number of units / plots",
        "hint": "count of flats, villas, or plots"
      },
      {
        "id": "delivery_model",
        "label": "Delivery model",
        "hint": "turnkey, milestone-based, joint venture"
      },
      {
        "id": "budget",
        "label": "Development budget",
        "hint": "total in lakhs/INR for project/phase"
      },
      {
        "id": "timeline",
        "label": "Delivery / phase timeline",
        "hint": "target completion or phase-wise delivery"
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone, WhatsApp, or email"
      },
      
    ],
    "optional": [
      {
        "id": "vendor_pref",
        "label": "Vendor / partner preference",
        "hint": "preferred contractors, consultants"
      },
      {
        "id": "compliance_focus",
        "label": "Compliance (property dev)",
        "hint": "RERA, local approvals, environmental"
      },
      {
        "id": "notes",
        "label": "Other development requirements",
        "hint": "marketing, sales, handover"
      },
      {
        "id": "preferred_start",
        "label": "When development to start",
        "hint": "ASAP, after approval, next financial year"
      },
      {
        "id": "must_haves",
        "label": "Must-haves for project",
        "hint": "amenities, specifications, branding"
      },
      {
        "id": "avoid",
        "label": "What to avoid",
        "hint": "delays, cost overruns, specific vendors"
      },
      {
        "id": "location",
        "label": "Project location",
        "hint": "city, zone, micro-market"
      },
      {
        "id": "risk_priorities",
        "label": "Risk priorities",
        "hint": "cost vs time vs quality focus"
      },
      {
        "id": "other_property",
        "label": "Any other property development detail",
        "hint": ""
      }
    ]
  },
  "home_automation": {
    "required": [
      {
        "id": "project_type",
        "label": "Property type",
        "hint": "apartment, villa, or independent house"
      },
      {
        "id": "property_type",
        "label": "Property stage",
        "hint": "new construction, existing home, or under renovation"
      },
      {
        "id": "size_sqft",
        "label": "Property area (sqft)",
        "hint": "total property size in square feet"
      },
      {
        "id": "rooms",
        "label": "Rooms / zones for automation",
        "hint": "whole home, living + bedrooms, or specific rooms"
      },
      {
        "id": "automation_scope",
        "label": "What to automate",
        "hint": "lighting, security, climate, curtains, or full home"
      },
      {
        "id": "budget",
        "label": "Automation budget",
        "hint": "rough budget in lakhs/INR"
      },
      {
        "id": "timeline",
        "label": "Project timeline",
        "hint": "ASAP, 1 month, 3 months, or flexible"
      },
      {
        "id": "location",
        "label": "Project location",
        "hint": "city and area"
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone, WhatsApp, or email"
      },

    ],
    "optional": [
      {
        "id": "current_systems",
        "label": "Existing electrical / systems",
        "hint": "wiring age, DB, existing switches, ACs"
      },
      {
        "id": "preferred_start",
        "label": "When to start automation work",
        "hint": "ASAP, after interior, next month"
      },
      {
        "id": "lighting_need",
        "label": "Smart lighting need",
        "hint": "dimmers, scenes, color, switches"
      },
      {
        "id": "security_need",
        "label": "Security automation",
        "hint": "CCTV, door access, sensors, alarms"
      },
      {
        "id": "climate_need",
        "label": "Climate / comfort",
        "hint": "AC control, curtains, sensors"
      },
      {
        "id": "notes",
        "label": "Other automation requirements",
        "hint": "voice control, app preference"
      },
      {
        "id": "must_haves",
        "label": "Must-haves (automation)",
        "hint": "voice, app, no cloud, etc."
      },
      {
        "id": "avoid",
        "label": "What to avoid",
        "hint": "brands, cloud-only, wireless-only"
      },
      {
        "id": "protocols",
        "label": "Preferred protocols",
        "hint": "Zigbee, Z-Wave, Wi-Fi, wired KNX"
      },
      {
        "id": "other_automation",
        "label": "Any other automation detail",
        "hint": ""
      }
    ]
  },
  "painting": {
    "required": [
      {
        "id": "project_type",
        "label": "Painting project type",
        "hint": "residential interior, exterior, commercial, both"
      },
      {
        "id": "size_sqft",
        "label": "Paintable area (sqft)",
        "hint": "wall + ceiling area or approx sqft to paint"
      },
      {
        "id": "surface_type",
        "label": "Surface to paint",
        "hint": "interior walls, ceiling, exterior walls, metal, wood"
      },
      {
        "id": "area_scope",
        "label": "Which areas to paint",
        "hint": "full house, specific rooms, exterior only, common areas"
      },
      {
        "id": "paint_type",
        "label": "Type of paint / finish",
        "hint": "emulsion, enamel, texture, waterproofing, primer"
      },
      {
        "id": "budget",
        "label": "Painting work budget",
        "hint": "total in lakhs/INR for paint + labour"
      },
      {
        "id": "timeline",
        "label": "When painting to be done",
        "hint": "completion date or handover"
      },
      {
        "id": "preferred_start",
        "label": "When to start painting",
        "hint": "ASAP, after repair, next week"
      },
      {
        "id": "location",
        "label": "Project location (city/area)",
        "hint": "city and area where painting work is"
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone, WhatsApp, or email"
      },
      
    ],
    "optional": [
      {
        "id": "color_preference",
        "label": "Color / shade preference",
        "hint": "specific colors, light/dark, mood"
      },
      {
        "id": "brand_preference",
        "label": "Paint brand preference",
        "hint": "Asian Paints, Berger, Dulux, or flexible"
      },
      {
        "id": "existing_paint",
        "label": "Current paint on surface",
        "hint": "emulsion, distemper, need scraping"
      },
      {
        "id": "notes",
        "label": "Other painting requirements",
        "hint": "child-safe, washable, etc."
      },
      {
        "id": "must_haves",
        "label": "Must-haves (painting)",
        "hint": "odorless, quick dry, warranty"
      },
      {
        "id": "avoid",
        "label": "What to avoid",
        "hint": "certain brands, colors, or methods"
      },
      {
        "id": "waterproofing_need",
        "label": "Waterproofing / exterior",
        "hint": "terrace, bathroom, exterior waterproofing"
      },
      {
        "id": "other_painting",
        "label": "Any other painting detail",
        "hint": ""
      }
    ]
  },
  "solar_services": {
    "required": [
      {
        "id": "project_type",
        "label": "Solar installation type",
        "hint": "residential rooftop, commercial, industrial, ground mount"
      },
      {
        "id": "roof_type",
        "label": "Roof type for solar",
        "hint": "flat RCC, slant, metal sheet, terrace",
        "skip_if_project_type": "ground mount"
      },
      {
        "id": "land_size_sqft",
        "label": "Available land area for panels (sqft)",
        "hint": "total open area available for ground mount panels",
        "only_if_project_type": "ground mount"
      },
      {
        "id": "land_type",
        "label": "Type of land for ground mount",
        "hint": "agricultural land, open plot, barren land",
        "only_if_project_type": "ground mount"
      },
      {
        "id": "size_sqft",
        "label": "Available roof / area for panels (sqft)",
        "hint": "unshaded area for panels in sqft"
      },
      {
        "id": "capacity_kw",
        "label": "Desired solar capacity (kW)",
        "hint": "target kW or \"suggest based on consumption\""
      },
      {
        "id": "grid_type",
        "label": "Grid connection type",
        "hint": "on-grid (net meter), off-grid, hybrid with battery"
      },
      {
        "id": "budget",
        "label": "Solar system budget",
        "hint": "total in lakhs/INR for panels + inverter + installation"
      },
      {
        "id": "financing",
        "label": "Financing need",
        "hint": "loan, EMI, upfront – how to pay"
      },
      {
        "id": "timeline",
        "label": "When to install solar",
        "hint": "ASAP, next month, after monsoon"
      },
      {
        "id": "preferred_start",
        "label": "Preferred installation start",
        "hint": "ASAP, next quarter, specific month"
      },
      {
        "id": "location",
        "label": "Project location (city/area)",
        "hint": "city and area where solar installation is"
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone, WhatsApp, or email"
      },
      
    ],
    "optional": [
      {
        "id": "subsidy_interest",
        "label": "Subsidy / scheme interest",
        "hint": "central/state subsidy, PM Surya Ghar"
      },
      {
        "id": "notes",
        "label": "Other solar requirements",
        "hint": "export limit, three-phase, etc."
      },
      {
        "id": "consumption_units",
        "label": "Current electricity consumption",
        "hint": "units per month from bill"
      },
      {
        "id": "orientation",
        "label": "Roof orientation",
        "hint": "south, east-west, north – if known"
      },
      {
        "id": "shade_issues",
        "label": "Shade on roof",
        "hint": "trees, adjacent building, water tank"
      },
      {
        "id": "other_solar",
        "label": "Any other solar detail",
        "hint": ""
      }
    ]
  },
  "electrical_services": {
    "required": [
      {
        "id": "project_type",
        "label": "Electrical work type",
        "hint": "residential, commercial, or industrial"
      },
      {
        "id": "scope_type",
        "label": "Scope of electrical work",
        "hint": "full rewiring, new installation, load upgrade, or safety audit"
      },
      {
        "id": "size_sqft",
        "label": "Property area (sqft)",
        "hint": "total property size in square feet"
      },
      {
        "id": "load_requirement",
        "label": "Approximate load (kW)",
        "hint": "approximate load in kW (e.g. 5kW, 10kW) or 'not sure'"
      },
      {
        "id": "safety_audit",
        "label": "Include safety audit",
        "hint": "yes or no"
      },
      {
        "id": "budget",
        "label": "Electrical work budget",
        "hint": "rough budget in lakhs/INR"
      },
      {
        "id": "timeline",
        "label": "Project timeline",
        "hint": "ASAP, 1 month, 3 months, or flexible"
      },
      {
        "id": "location",
        "label": "Project location",
        "hint": "city and area"
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone, WhatsApp, or email"
      },

    ],
    "optional": [
      {
        "id": "current_system",
        "label": "Current electrical setup",
        "hint": "wiring age, DB capacity, meter type"
      },
      {
        "id": "preferred_start",
        "label": "When to start electrical work",
        "hint": "ASAP, after demolition"
      },
      {
        "id": "backup_need",
        "label": "Backup / inverter need",
        "hint": "inverter capacity, battery, solar integration"
      },
      {
        "id": "automation_need",
        "label": "Smart / automation need",
        "hint": "smart switches, home automation scope"
      },
      {
        "id": "notes",
        "label": "Other electrical requirements",
        "hint": "dedicated lines, surge protection"
      },
      {
        "id": "property_age",
        "label": "Property / building age",
        "hint": "years – for wiring condition context"
      },
      {
        "id": "wiring_type",
        "label": "Wiring preference",
        "hint": "concealed, surface, PVC, FR"
      },
      {
        "id": "must_haves",
        "label": "Must-haves (electrical)",
        "hint": "MCB upgrade, earthing, dedicated points"
      },
      {
        "id": "avoid",
        "label": "What to avoid",
        "hint": "certain brands, methods"
      },
      {
        "id": "other_electrical",
        "label": "Any other electrical detail",
        "hint": ""
      }
    ]
  },
  "plumbing_services": {
    "required": [
      {
        "id": "project_type",
        "label": "Plumbing work type",
        "hint": "residential, commercial, society"
      },
      {
        "id": "scope_type",
        "label": "Scope of plumbing work",
        "hint": "new plumbing, repair, renovation, bathroom addition"
      },
      {
        "id": "budget",
        "label": "Plumbing work budget",
        "hint": "total in lakhs/INR for labour + material"
      },
      {
        "id": "preferred_start",
        "label": "When to start plumbing work",
        "hint": "ASAP, after tiling"
      },
      {
        "id": "location",
        "label": "Project location (city/area)",
        "hint": "city and area where plumbing work is"
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone, WhatsApp, or email"
      },
      {
        "id": "water_source",
        "label": "Water source at property",
        "hint": "municipal, borewell, overhead tank, sump"
      },
      {
        "id": "current_issues",
        "label": "Current plumbing issues",
        "hint": "leak, low pressure, blockage, no water"
      },
      {
        "id": "property_age",
        "label": "Property / building age",
        "hint": "years – for pipe condition and replacement"
      },
      
    ],
    "optional": [
      {
        "id": "hot_water_need",
        "label": "Hot water requirement",
        "hint": "geyser count, solar, instant heater"
      },
      {
        "id": "filter_need",
        "label": "Water filter / purification",
        "hint": "RO, UV, whole house – if needed"
      },
      {
        "id": "notes",
        "label": "Other plumbing requirements",
        "hint": "concealed pipes, chase, etc."
      },
      {
        "id": "timeline",
        "label": "When to complete plumbing",
        "hint": "ASAP, with renovation, specific date"
      },
      {
        "id": "must_haves",
        "label": "Must-haves (plumbing)",
        "hint": "CPVC only, no lead, warranty"
      },
      {
        "id": "avoid",
        "label": "What to avoid",
        "hint": "certain materials, open pipes"
      },
      {
        "id": "material_pref",
        "label": "Pipe material preference",
        "hint": "CPVC, PVC, PPR, galvanized"
      },
      {
        "id": "bathroom_count",
        "label": "Number of bathrooms",
        "hint": "for scope and quote"
      },
      {
        "id": "other_plumbing",
        "label": "Any other plumbing detail",
        "hint": ""
      }
    ]
  },
  "irrigation_automation": {
    "required": [
      {
        "id": "project_type",
        "label": "Irrigation project type",
        "hint": "farm, garden, lawn, nursery, orchard"
      },
      {
        "id": "crop_type",
        "label": "Crop or plantation type",
        "hint": "field crop, vegetable, lawn, horticulture, flowers"
      },
      {
        "id": "land_size_sqft",
        "label": "Area to irrigate (sqft)",
        "hint": "total land or plot size in sqft"
      },
      {
        "id": "water_source",
        "label": "Water source for irrigation",
        "hint": "borewell, canal, tank, open well, municipal"
      },
      {
        "id": "current_system",
        "label": "Existing irrigation (if any)",
        "hint": "none, manual, drip, sprinkler, flood"
      },
      {
        "id": "budget",
        "label": "Irrigation system budget",
        "hint": "total in lakhs/INR for drip/sprinkler + automation"
      },
      {
        "id": "timeline",
        "label": "When to install irrigation",
        "hint": "ASAP, before season, next month"
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone, WhatsApp, or email"
      },
      
    ],
    "optional": [
      {
        "id": "soil_type",
        "label": "Soil type",
        "hint": "clay, loam, sandy – if known"
      },
      {
        "id": "sensor_need",
        "label": "Sensor need",
        "hint": "soil moisture, weather, flow – yes/no"
      },
      {
        "id": "notes",
        "label": "Other irrigation requirements",
        "hint": "slope, zones, organic"
      },
      {
        "id": "preferred_start",
        "label": "When to start irrigation work",
        "hint": "ASAP, next season"
      },
      {
        "id": "must_haves",
        "label": "Must-haves (irrigation)",
        "hint": "drip only, fertigation, mobile control"
      },
      {
        "id": "avoid",
        "label": "What to avoid",
        "hint": "overhead in certain areas, etc."
      },
      {
        "id": "power_avail",
        "label": "Power at site",
        "hint": "grid, solar, no power"
      },
      {
        "id": "automation_level",
        "label": "Automation level",
        "hint": "manual timer, smart schedule, app control"
      },
      {
        "id": "other_irrigation",
        "label": "Any other irrigation detail",
        "hint": ""
      }
    ]
  },
  "event_management": {
    "required": [
      {
        "id": "event_type",
        "label": "Event format",
        "hint": "conference, wedding, seminar, party, exhibition, award night"
      },
      {
        "id": "project_type",
        "label": "Type of event",
        "hint": "corporate, wedding, social, product launch, conference"
      },
      {
        "id": "guest_count",
        "label": "Expected guest count",
        "hint": "approx number of guests or attendees"
      },
      {
        "id": "venue_type",
        "label": "Venue type",
        "hint": "indoor, outdoor, hotel, farmhouse, auditorium, lawn"
      },
      {
        "id": "size_sqft",
        "label": "Venue size / scale (sqft)",
        "hint": "approx venue or seating area in sqft"
      },
      {
        "id": "budget",
        "label": "Event budget",
        "hint": "total in lakhs/INR for event management"
      },
      {
        "id": "timeline",
        "label": "Event date / planning timeline",
        "hint": "event date or \"need to fix date\""
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone, WhatsApp, or email"
      },
      
    ],
    "optional": [
      {
        "id": "catering_need",
        "label": "Catering in scope",
        "hint": "included in package or separate vendor"
      },
      {
        "id": "av_need",
        "label": "AV and tech need",
        "hint": "sound, mics, screen, LED, recording"
      },
      {
        "id": "theme",
        "label": "Event theme / mood",
        "hint": "corporate, traditional, theme party"
      },
      {
        "id": "notes",
        "label": "Other event requirements",
        "hint": "VIP, protocol, branding"
      },
      {
        "id": "preferred_start",
        "label": "When to start planning",
        "hint": "ASAP, months before event"
      },
      {
        "id": "must_haves",
        "label": "Must-haves (event)",
        "hint": "certain venue, celebrity, live band"
      },
      {
        "id": "avoid",
        "label": "What to avoid",
        "hint": "certain cuisines, venues, or elements"
      },
      {
        "id": "vendor_pref",
        "label": "Vendor / artist preference",
        "hint": "preferred or blacklisted"
      },
      {
        "id": "other_event",
        "label": "Any other event detail",
        "hint": ""
      }
    ]
  },
  "farm_infrastructure": {
    "required": [
      {
        "id": "project_type",
        "label": "Farm / agri project type",
        "hint": "farm, dairy, poultry, mixed agri, aquaculture"
      },
      {
        "id": "primary_use",
        "label": "Primary farm activity",
        "hint": "main crop, dairy, poultry, mixed"
      },
      {
        "id": "land_size",
        "label": "Land size (sqft or acres)",
        "hint": "total farm or plot area"
      },
      {
        "id": "water_source",
        "label": "Water source on farm",
        "hint": "borewell, canal, pond, tank, open well"
      },
      {
        "id": "power_avail",
        "label": "Power at farm",
        "hint": "grid, solar, generator, no power"
      },
      {
        "id": "budget",
        "label": "Farm infrastructure budget",
        "hint": "total in lakhs/INR for structures and setup"
      },
      {
        "id": "timeline",
        "label": "When to complete farm infra",
        "hint": "ASAP, before season, phase-wise"
      },
      {
        "id": "contact_pref",
        "label": "How to reach you",
        "hint": "phone, WhatsApp, or email"
      },
      
    ],
    "optional": [
      {
        "id": "irrigation_need",
        "label": "Irrigation setup need",
        "hint": "drip, sprinkler, full irrigation – yes/no"
      },
      {
        "id": "greenhouse_need",
        "label": "Greenhouse / polyhouse",
        "hint": "if needed – size or yes/no"
      },
      {
        "id": "storage_need",
        "label": "Storage requirement",
        "hint": "godown, cold storage, silo"
      },
      {
        "id": "notes",
        "label": "Other farm requirements",
        "hint": "organic, certification, labour"
      },
      {
        "id": "preferred_start",
        "label": "When to start farm work",
        "hint": "ASAP, next season"
      },
      {
        "id": "must_haves",
        "label": "Must-haves (farm infra)",
        "hint": "shed size, flooring, ventilation"
      },
      {
        "id": "avoid",
        "label": "What to avoid",
        "hint": "certain materials, designs"
      },
      {
        "id": "structures",
        "label": "Structures needed",
        "hint": "cattle shed, boundary, warehouse, pump house"
      },
      {
        "id": "other_farm",
        "label": "Any other farm infra detail",
        "hint": ""
      }
    ]
  }
}

// Canned data and agent responses for the prototype
window.PROTO_DATA = (() => {
  const CHWS = [
    { id: "chw-001", name: "Achieng Wanjala", area: "Mumias West", encounters30: 99,  encounters7: 22, status: "warn",   trend: [4,3,2,3,4,3,3] },
    { id: "chw-002", name: "Brenda Kagwiria", area: "Lurambi",     encounters30: 16,  encounters7: 0,  status: "alert",  trend: [0,0,2,0,0,0,0] },
    { id: "chw-003", name: "Charles Otieno",  area: "Shinyalu",    encounters30: 132, encounters7: 31, status: "ok",     trend: [4,5,4,5,5,4,4] },
    { id: "chw-004", name: "Doreen Mukhwana", area: "Ikolomani",   encounters30: 128, encounters7: 30, status: "ok",     trend: [5,4,5,4,4,4,4] },
    { id: "chw-005", name: "Elphas Wekesa",   area: "Malava",      encounters30: 121, encounters7: 28, status: "ok",     trend: [4,4,4,4,4,4,4] },
    { id: "chw-009", name: "Irene Nasimiyu",  area: "Mumias East",  encounters30: 140, encounters7: 34, status: "top",    trend: [5,5,5,5,5,4,5] },
    { id: "chw-014", name: "Naomi Shitanda",  area: "Khwisero",    encounters30: 119, encounters7: 27, status: "ok",     trend: [4,4,4,4,4,4,3] },
    { id: "chw-019", name: "Sammy Barasa",    area: "Navakholo",   encounters30: 140, encounters7: 33, status: "top",    trend: [5,5,5,4,5,5,4] },
    { id: "chw-022", name: "Vincent Mudaki",  area: "Lugari",      encounters30: 102, encounters7: 24, status: "ok",     trend: [3,4,3,4,3,4,3] },
    { id: "chw-027", name: "Zipporah Indasi", area: "Likuyani",    encounters30: 94,  encounters7: 20, status: "warn",   trend: [3,3,3,2,3,3,3] },
  ];

  // Daily team total over last 30 days, ending May 1
  const VISITS_BY_DAY = [
    98,112,121,108, 96, 41, 18,
   115,127,131,118,124, 52, 24,
   118,129,135,121,116, 48, 20,
   122,130,128,119,117, 51, 22,
   125, 0
  ];
  const VISITS_LABELS = (() => {
    const arr = [];
    const end = new Date(2026, 4, 1); // May 1 2026
    for (let i = 29; i >= 0; i--) {
      const d = new Date(end); d.setDate(end.getDate() - i);
      arr.push(d);
    }
    return arr;
  })();

  // --- Briefing response (structured, not markdown) ---
  const BRIEFING = {
    headline: "Team output is on-trend, but two CHWs need attention and Friday May 1 saw zero recorded activity.",
    period: "Apr 11 → May 10 · 30-day lookback",
    sections: [
      {
        kind: "stat-row",
        stats: [
          { label: "Team encounters",  value: "3,748", delta: "+4.2%", deltaTone: "ok",    sub: "vs prior 30 days" },
          { label: "Active CHWs",      value: "29 / 30", delta: "−1",  deltaTone: "warn",  sub: "chw-002 inactive 7d" },
          { label: "Patients touched", value: "517",   delta: "+11",   deltaTone: "ok",    sub: "of 581 in roster" },
          { label: "Mean / CHW",       value: "125",   delta: "σ 31",  deltaTone: "muted", sub: "median 124" },
        ],
      },
      {
        kind: "callout",
        tone: "alert",
        title: "Zero activity on Fri May 1",
        body: "Team-wide stoppage — likely a public holiday gap, but worth confirming. visits_by_day shows the only zero-day in the window.",
        evidence: ["visits_by_day", "team_activity_summary"],
      },
      {
        kind: "ranked",
        title: "Top performers (30d)",
        tone: "ok",
        items: [
          { id: "chw-009", primary: "140 encounters", secondary: "34 in last 7d · Mumias East" },
          { id: "chw-019", primary: "140 encounters", secondary: "33 in last 7d · Navakholo" },
        ],
      },
      {
        kind: "ranked",
        title: "Needs supervisor follow-up",
        tone: "alert",
        items: [
          { id: "chw-002", primary: "16 encounters · 0 in last 7d", secondary: "−87% vs team mean. Last log Apr 18. Likely absence — call today." },
          { id: "chw-001", primary: "99 encounters · 22 in last 7d", secondary: "Trending down 3 weeks running. Possible caseload issue in Mumias West." },
        ],
      },
      {
        kind: "callout",
        tone: "warn",
        title: "Data quality",
        body: "find_patient name search returned 0 hits on a smoke query — OpenMRS FHIR2 composite name parameter regression. Patient-by-name lookups will fall through.",
        evidence: ["find_patient"],
      },
    ],
    sources: ["team_activity_summary(30)", "chw_inactivity(7,0)", "visits_by_day(30)", "list_chws()"],
  };

  // Tool-execution timeline (used for the "agent thinking" state)
  const BRIEFING_PLAN = [
    { tool: "list_chws",              args: "()",                 ms: 410,  rows: 30 },
    { tool: "team_activity_summary",  args: "(days=30)",          ms: 1820, rows: 30 },
    { tool: "chw_inactivity",         args: "(days=7, max=0)",    ms: 740,  rows: 1  },
    { tool: "visits_by_day",          args: "(days=30)",          ms: 980,  rows: 30 },
    { tool: "recent_deaths",          args: "(days=30)",          ms: 360,  rows: 2  },
  ];

  // Follow-up canned answers, keyed by trigger keywords
  const FOLLOWUPS = [
    {
      match: /chw-002|brenda/i,
      plan: [
        { tool: "find_patient",       args: "(query=\"chw-002\")", ms: 220, rows: 0 },
        { tool: "count_chw_encounters", args: "(chw-002, 30)",     ms: 480, rows: 1 },
        { tool: "chw_patient_panel",  args: "(chw-002, 30, 50)",  ms: 1240, rows: 4 },
      ],
      response: {
        headline: "chw-002 (Brenda Kagwiria) — last activity Apr 18, 22 days ago.",
        sections: [
          {
            kind: "stat-row",
            stats: [
              { label: "Encounters 30d", value: "16",  delta: "team avg 125", deltaTone: "alert", sub: "−87%" },
              { label: "Encounters 7d",  value: "0",   delta: "0 visits", deltaTone: "alert", sub: "no logs" },
              { label: "Distinct patients",  value: "4", delta: "panel size", deltaTone: "muted", sub: "expected 18-22" },
              { label: "Last encounter", value: "Apr 18", delta: "22d ago", deltaTone: "alert", sub: "Mary Wafula" },
            ],
          },
          {
            kind: "callout",
            tone: "alert",
            title: "Suggested action",
            body: "Pattern matches the 'vacation absence' scenario in the seeded scenarios. Call CHW directly; if unreachable, redistribute Lurambi caseload to chw-014 and chw-022.",
            evidence: ["chw_patient_panel", "count_chw_encounters"],
          },
          {
            kind: "panel",
            title: "Recent patient panel",
            rows: [
              { left: "Mary Wafula",      mid: "F · 34", right: "Apr 18 · 5 encs" },
              { left: "Joseph Lihanda",   mid: "M · 67", right: "Apr 16 · 4 encs" },
              { left: "Faith Mukasa",     mid: "F · 28", right: "Apr 14 · 4 encs" },
              { left: "Patrick Shikuku",  mid: "M · 52", right: "Apr 11 · 3 encs" },
            ],
          },
        ],
        sources: ["count_chw_encounters", "chw_patient_panel(chw-002, 30)"],
      },
    },
    {
      match: /chw-009|irene|top|patient panel/i,
      plan: [
        { tool: "team_activity_summary", args: "(days=30)", ms: 1610, rows: 30 },
        { tool: "chw_patient_panel",     args: "(chw-009, 30, 50)", ms: 1380, rows: 20 },
      ],
      response: {
        headline: "chw-009 (Irene Nasimiyu) — top-of-roster, 20 distinct patients in 30 days.",
        sections: [
          {
            kind: "stat-row",
            stats: [
              { label: "Encounters 30d", value: "140", delta: "+12% vs mean", deltaTone: "ok",    sub: "rank 1 of 30" },
              { label: "Encounters 7d",  value: "34",  delta: "consistent",   deltaTone: "ok",    sub: "no Friday slump" },
              { label: "Distinct patients", value: "20", delta: "high reach", deltaTone: "ok",    sub: "median 14" },
              { label: "Days active",    value: "26 / 30", delta: "−1 (May 1)", deltaTone: "muted", sub: "Sundays off" },
            ],
          },
          {
            kind: "panel",
            title: "Patient panel — top 6 by encounters",
            rows: [
              { left: "Grace Wanjiru",   mid: "F · 41 · ANC",       right: "May 1 · 9 encs" },
              { left: "Daniel Khaemba",  mid: "M · 58 · HTN",       right: "Apr 30 · 8 encs" },
              { left: "Eunice Atieno",   mid: "F · 32 · postpartum", right: "Apr 30 · 7 encs" },
              { left: "Mercy Sifuna",    mid: "F · 24 · ANC",       right: "Apr 29 · 7 encs" },
              { left: "Brian Mukoya",    mid: "M · 6 · immunization",right: "Apr 28 · 6 encs" },
              { left: "Hellen Wekhuyi",  mid: "F · 71 · diabetes",   right: "Apr 27 · 6 encs" },
            ],
          },
        ],
        sources: ["chw_patient_panel(chw-009, 30, 50)"],
      },
    },
    {
      match: /may 1|friday|stop|zero|inactiv/i,
      plan: [
        { tool: "visits_by_day",   args: "(days=30)",       ms: 940, rows: 30 },
        { tool: "chw_inactivity",  args: "(days=1, max=0)", ms: 510, rows: 30 },
        { tool: "recent_deaths",   args: "(days=7)",        ms: 320, rows: 0 },
      ],
      response: {
        headline: "May 1 was a team-wide zero — every CHW logged 0 encounters. Likely a holiday, not a data outage.",
        sections: [
          {
            kind: "stat-row",
            stats: [
              { label: "CHWs active May 1", value: "0 / 30", delta: "vs 28 avg", deltaTone: "alert", sub: "team-wide" },
              { label: "Prior Friday avg",  value: "118",    delta: "expected", deltaTone: "muted", sub: "Apr 4–24" },
              { label: "Sat May 2 logs",    value: "—",      delta: "no data",  deltaTone: "muted", sub: "after window" },
              { label: "Pattern",           value: "Holiday", delta: "Labour Day", deltaTone: "ok",   sub: "Kenya public holiday" },
            ],
          },
          {
            kind: "callout",
            tone: "ok",
            title: "Most likely cause",
            body: "May 1 is Labour Day in Kenya — uniform zero across all 30 CHWs is consistent with a planned non-working day, not a system failure or app outage.",
            evidence: ["chw_inactivity", "visits_by_day"],
          },
        ],
        sources: ["visits_by_day(30)", "chw_inactivity(1,0)"],
      },
    },
  ];

  return { CHWS, VISITS_BY_DAY, VISITS_LABELS, BRIEFING, BRIEFING_PLAN, FOLLOWUPS };
})();

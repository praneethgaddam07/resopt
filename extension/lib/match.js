(function(root) {
  root.RESOPT_match = {
    keywords: function(text, skills, limit, title, company) {
      if (!skills || !Array.isArray(skills)) {
        skills = [];
      }
      return skills.slice(0, limit || 16);
    },
    fit: function(resumeText, kw) {
      if (!kw || kw.length === 0) return { pct: 0, verdict: "Low match", covered: [], missing: [] };
      const resumeLower = (resumeText || "").toLowerCase();
      let covered = [];
      let missing = [];
      kw.forEach(k => {
        if (resumeLower.includes(k.toLowerCase())) {
          covered.push(k);
        } else {
          missing.push(k);
        }
      });
      const pct = Math.round((covered.length / kw.length) * 100);
      let verdict = pct >= 65 ? "Good match" : pct >= 40 ? "Medium match" : "Low match";
      return { pct, verdict, covered, missing };
    }
  };
})(typeof window !== 'undefined' ? window : this);

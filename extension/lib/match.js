(function(root) {
  root.RESOPT_match = {
    keywords: function(text, skills, limit, title, company) {
      if (!skills || !Array.isArray(skills)) {
        skills = [];
      }
      return skills.slice(0, limit || 16);
    },
    fit: function(resumeText, kw) {
      if (!kw || kw.length === 0) return { score: 0, cover: [], gap: [] };
      const resumeLower = (resumeText || "").toLowerCase();
      let cover = [];
      let gap = [];
      kw.forEach(k => {
        if (resumeLower.includes(k.toLowerCase())) {
          cover.push(k);
        } else {
          gap.push(k);
        }
      });
      const score = Math.round((cover.length / kw.length) * 100);
      return { score, cover, gap };
    }
  };
})(typeof window !== 'undefined' ? window : this);

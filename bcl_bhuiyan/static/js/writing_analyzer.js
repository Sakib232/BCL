/**
 * ==============================================================================
 * IELTS Bhuiyan - Automated Writing Exam Analyzer & Practice Band Scoring Engine
 * ==============================================================================
 * Pure Client-Side JavaScript Analyzer adhering to Official IELTS Writing Descriptors:
 *   1. Task Achievement (Task 1) / Task Response (Task 2)
 *   2. Coherence and Cohesion (CC)
 *   3. Lexical Resource (LR)
 *   4. Grammatical Range and Accuracy (GRA)
 *
 * Weighting: Task 1 = 33.3% (1/3), Task 2 = 66.7% (2/3)
 * Standard IELTS Band scale: 0.0 to 9.0 in steps of 0.5
 */

(function(window) {
    "use strict";

    // --------------------------------------------------------------------------
    // 1. DICTIONARIES & PATTERNS
    // --------------------------------------------------------------------------

    // Cohesive devices categorized by rhetorical function
    const COHESIVE_DEVICES = {
        addition: [
            "furthermore", "moreover", "in addition", "additionally", "besides",
            "what is more", "not only", "as well as", "equally important"
        ],
        contrast: [
            "however", "in contrast", "on the other hand", "nevertheless",
            "nonetheless", "conversely", "whereas", "although", "even though",
            "while", "despite", "in spite of", "on the contrary"
        ],
        result: [
            "consequently", "therefore", "as a result", "thus", "hence",
            "for this reason", "leads to", "resulting in", "accordingly"
        ],
        exemplification: [
            "for example", "for instance", "to illustrate", "such as",
            "namely", "as an illustration", "in particular"
        ],
        overview_conclusion: [
            "overall", "in conclusion", "to conclude", "to sum up",
            "in summary", "on the whole", "all in all", "in brief"
        ],
        sequencing: [
            "firstly", "secondly", "thirdly", "finally", "subsequently",
            "initially", "to begin with", "in the first place"
        ],
        stance: [
            "in my opinion", "i believe", "from my perspective",
            "it is evident", "it is apparent", "undoubtedly", "arguably"
        ]
    };

    // Flattened cohesive phrases for regex matching (longest first to avoid partial matches)
    const ALL_COHESIVE_PHRASES = Object.values(COHESIVE_DEVICES).flat().sort((a, b) => b.length - a.length);

    // Common stop words to exclude from lexical diversity / repetition calculations
    const STOP_WORDS = new Set([
        "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it",
        "for", "not", "on", "with", "he", "as", "you", "do", "at", "this", "but",
        "his", "by", "from", "they", "we", "say", "her", "she", "or", "an", "will",
        "my", "one", "all", "would", "there", "their", "what", "so", "up", "out",
        "if", "about", "who", "get", "which", "go", "me", "when", "make", "can",
        "like", "time", "no", "just", "him", "know", "take", "people", "into",
        "year", "your", "good", "some", "could", "them", "see", "other", "than",
        "then", "now", "look", "only", "come", "its", "over", "think", "also",
        "back", "after", "use", "two", "how", "our", "work", "first", "well",
        "way", "even", "new", "want", "because", "any", "these", "give", "day",
        "most", "us", "is", "are", "was", "were", "been", "has", "had"
    ]);

    // IELTS Academic Word List (AWL) - High-Frequency Academic Vocabulary
    const ACADEMIC_WORDS = new Set([
        "abandon", "abstract", "academic", "access", "accommodate", "accompany",
        "accumulate", "accurate", "achieve", "acknowledge", "acquire", "adapt",
        "adequate", "adjacent", "adjust", "administrate", "adult", "advocate",
        "affect", "aggregate", "aid", "albeit", "allocate", "alter", "alternative",
        "ambiguous", "amend", "analogy", "analyse", "analysis", "annual", "anticipate",
        "apparent", "append", "appreciate", "approach", "appropriate", "approximate",
        "arbitrary", "area", "aspect", "assemble", "assess", "assign", "assist",
        "assume", "assure", "attach", "attain", "attitude", "attribute", "author",
        "authority", "automate", "available", "aware", "behalf", "benefit", "bias",
        "bond", "brief", "bulk", "capable", "capacity", "category", "cease", "challenge",
        "channel", "chapter", "chart", "chemical", "circumstance", "cite", "civil",
        "clarify", "classic", "clause", "clear", "coincide", "collapse", "colleague",
        "commence", "comment", "commission", "commit", "commodity", "communicate",
        "community", "compatible", "compensate", "compile", "complement", "complex",
        "component", "compound", "comprehensive", "comprise", "compute", "conceive",
        "concentrate", "concept", "conclude", "concurrent", "conduct", "confer",
        "confine", "confirm", "conflict", "conform", "consent", "consequence",
        "consequent", "considerable", "consist", "consistent", "constant",
        "constitute", "constrain", "construct", "consult", "consume", "contact",
        "contemporary", "context", "contract", "contradict", "contrary", "contrast",
        "contribute", "controversy", "convene", "converse", "convert", "convince",
        "cooperate", "coordinate", "core", "corporate", "correspond", "couple",
        "create", "credit", "criteria", "crucial", "culture", "currency", "cycle",
        "data", "debate", "decade", "decline", "deduce", "define", "definite",
        "demonstrate", "denote", "deny", "depress", "derive", "design", "despite",
        "detect", "deviate", "device", "devote", "differentiate", "dimension",
        "diminish", "discrete", "discriminate", "displace", "display", "dispose",
        "distinct", "distort", "distribute", "diverse", "document", "domain",
        "domestic", "dominate", "draft", "drama", "duration", "dynamic", "economy",
        "element", "eliminate", "emerge", "emphasis", "empirical", "enable",
        "encounter", "energy", "enforce", "enhance", "enormous", "ensure", "entity",
        "environment", "equate", "equip", "equivalent", "erode", "error", "establish",
        "estate", "estimate", "ethic", "ethnic", "evaluate", "eventual", "evident",
        "evolve", "exceed", "exclude", "exhibit", "expand", "expert", "explicit",
        "exploit", "export", "expose", "external", "extract", "facilitate", "factor",
        "feature", "federal", "fee", "file", "final", "finance", "finite", "flexible",
        "fluctuate", "focus", "format", "formula", "forthcoming", "foundation",
        "framework", "function", "fund", "fundamental", "furthermore", "gender",
        "generate", "generation", "globe", "goal", "grade", "grant", "guarantee",
        "guideline", "hence", "hierarchy", "highlight", "hypothesis", "identical",
        "identify", "ideology", "ignorant", "illustrate", "image", "immigrate",
        "impact", "implement", "implicate", "implicit", "imply", "impose", "incentive",
        "incidence", "incline", "income", "incorporate", "index", "indicate",
        "individual", "induce", "inevitable", "infer", "infrastructure", "inherent",
        "inhibit", "initial", "initiate", "injure", "innovate", "input", "insert",
        "insight", "inspect", "instance", "institute", "instruct", "integral",
        "integrate", "integrity", "intelligence", "intense", "interact", "intermediate",
        "internal", "interpret", "interval", "intervene", "intrinsic", "invest",
        "investigate", "invoke", "involve", "isolate", "issue", "item", "job",
        "journal", "justify", "label", "labour", "layer", "lecture", "legal",
        "legislate", "levy", "liberal", "license", "likewise", "link", "locate",
        "logic", "maintain", "major", "manipulate", "manual", "margin", "mature",
        "maximize", "mechanism", "media", "mediate", "medical", "medium", "method",
        "migrate", "military", "minimal", "minimize", "minimum", "ministry", "minor",
        "mode", "modify", "monitor", "motive", "mutual", "negate", "network",
        "neutral", "nevertheless", "nonetheless", "norm", "normal", "notion",
        "nuclear", "objective", "obtain", "obvious", "occupy", "occur", "odd",
        "offset", "ongoing", "option", "orient", "outcome", "output", "overall",
        "overlap", "overseas", "panel", "paradigm", "paragraph", "parallel",
        "parameter", "participate", "partner", "passive", "perceive", "percent",
        "period", "persist", "perspective", "phase", "phenomenon", "philosophy",
        "physical", "plus", "policy", "portion", "pose", "positive", "potential",
        "practitioner", "precede", "precise", "predict", "predominant", "preliminary",
        "presume", "previous", "primary", "prime", "principal", "principle", "prior",
        "priority", "proceed", "process", "professional", "prohibit", "project",
        "promote", "proportion", "prospect", "protocol", "psychology", "publication",
        "publish", "purchase", "pursue", "qualitative", "quote", "radical", "random",
        "range", "ratio", "rational", "react", "recover", "refine", "regime",
        "region", "register", "regulate", "reinforce", "reject", "relax", "release",
        "relevant", "reluctance", "rely", "remove", "require", "research", "reside",
        "resolve", "resource", "respond", "restore", "restrain", "restrict", "retain",
        "reveal", "revenue", "reverse", "revise", "revolution", "rigid", "role",
        "route", "scenario", "schedule", "scheme", "scope", "section", "sector",
        "secure", "seek", "select", "sequence", "series", "sex", "shift",
        "significant", "similar", "simulate", "site", "so-called", "sole", "somewhat",
        "source", "specific", "specify", "sphere", "stable", "statistic", "status",
        "straightforward", "strategy", "stress", "structure", "style", "submit",
        "subordinate", "subsequent", "subsidy", "substitute", "successor", "sufficient",
        "sum", "summary", "supplement", "survey", "survive", "suspend", "sustain",
        "symbol", "tape", "target", "task", "team", "technical", "technique",
        "technology", "temporary", "tense", "terminate", "text", "theme", "theory",
        "thereby", "thesis", "topic", "trace", "tradition", "transfer", "transform",
        "transit", "transmit", "transport", "trend", "trigger", "ultimate", "undergo",
        "underlie", "undertake", "uniform", "unify", "unique", "utilise", "valid",
        "vary", "vehicle", "version", "via", "violate", "virtual", "visible",
        "vision", "visual", "volume", "voluntary", "welfare", "whereas", "whereby",
        "widespread"
    ]);

    // Subordinating conjunctions & markers for Grammatical Range (complex sentences)
    const COMPLEX_SENTENCE_MARKERS = [
        "although", "even though", "though", "because", "since", "while",
        "whereas", "unless", "until", "provided that", "as long as", "in order that",
        "so that", "whether", "if", "despite the fact", "in spite of the fact",
        "which", "who", "whom", "whose", "whereby"
    ];

    // --------------------------------------------------------------------------
    // 2. TEXT PROCESSING HELPERS
    // --------------------------------------------------------------------------

    function cleanText(raw) {
        if (!raw) return "";
        return raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
    }

    function extractWords(text) {
        if (!text) return [];
        const matches = text.match(/\b[A-Za-z0-9]+(?:'[A-Za-z]+)?\b/g);
        return matches || [];
    }

    function extractSentences(text) {
        if (!text) return [];
        // Match sentence terminators (. ! ?) followed by whitespace or EOF
        const raw = text.split(/(?<=[.!?])\s+/);
        return raw.map(s => s.trim()).filter(s => s.length > 3);
    }

    function extractParagraphs(text) {
        if (!text) return [];
        const raw = text.split(/\n\s*\n/);
        return raw.map(p => p.trim()).filter(p => p.length > 0);
    }

    function roundToIELTSHalfBand(score) {
        const clamped = Math.max(0, Math.min(9, score));
        const floor = Math.floor(clamped);
        const diff = clamped - floor;
        if (diff < 0.25) return floor;
        if (diff < 0.75) return floor + 0.5;
        return floor + 1.0;
    }

    // --------------------------------------------------------------------------
    // 3. TASK-LEVEL SCORING ENGINE
    // --------------------------------------------------------------------------

    /**
     * Analyzes a single writing task (Task 1 or Task 2).
     * @param {string} text - The candidate's response
     * @param {number} taskNumber - 1 or 2
     * @returns {Object} Comprehensive evaluation metrics and scores
     */
    function analyzeTask(text, taskNumber) {
        const cleaned = cleanText(text);
        const words = extractWords(cleaned);
        const wordCount = words.length;
        const paragraphs = extractParagraphs(cleaned);
        const sentences = extractSentences(cleaned);
        const taskNum = (taskNumber === 1 || taskNumber === 2) ? taskNumber : 2;
        const targetWords = taskNum === 1 ? 150 : 250;

        // If no response was provided
        if (wordCount === 0) {
            return {
                taskNumber: taskNum,
                wordCount: 0,
                targetWords: targetWords,
                isUnderlength: true,
                paragraphCount: 0,
                sentenceCount: 0,
                scores: {
                    taskAchievement: 0.0,
                    coherenceCohesion: 0.0,
                    lexicalResource: 0.0,
                    grammaticalRange: 0.0,
                    taskAverage: 0.0,
                },
                diagnostics: {
                    ttr: 0,
                    academicDensity: 0,
                    academicWordsFound: [],
                    cohesiveDevicesFound: [],
                    repeatedWords: [],
                    avgSentenceLength: 0,
                    complexSentenceCount: 0
                },
                feedback: ["No response entered for this task."]
            };
        }

        // --- A. TASK ACHIEVEMENT / TASK RESPONSE (TA / TR) ---
        let taScore = 6.0;
        const taFeedback = [];

        // Word count penalties
        if (taskNum === 1) {
            if (wordCount >= 170) {
                taScore = 7.0;
                taFeedback.push(`Excellent response length (${wordCount} words, exceeds 150 minimum).`);
            } else if (wordCount >= 150) {
                taScore = 6.5;
                taFeedback.push(`Adequate word count (${wordCount} words, satisfies 150 minimum).`);
            } else if (wordCount >= 135) {
                taScore = 5.5;
                taFeedback.push(`Slightly under length (${wordCount}/150 words). Caps Task Achievement at Band 5.5.`);
            } else if (wordCount >= 100) {
                taScore = 5.0;
                taFeedback.push(`Under length penalty (${wordCount}/150 words). Significantly limits task completion.`);
            } else {
                taScore = 4.0;
                taFeedback.push(`Severely short response (${wordCount}/150 words). Lacks necessary detail.`);
            }
        } else {
            // Task 2
            if (wordCount >= 280) {
                taScore = 7.0;
                taFeedback.push(`Thorough, well-developed length (${wordCount} words, exceeds 250 minimum).`);
            } else if (wordCount >= 250) {
                taScore = 6.5;
                taFeedback.push(`Satisfies 250-word minimum (${wordCount} words).`);
            } else if (wordCount >= 225) {
                taScore = 5.5;
                taFeedback.push(`Under 250 words (${wordCount}/250 words). Automatic length deduction applied.`);
            } else if (wordCount >= 160) {
                taScore = 5.0;
                taFeedback.push(`Significantly under length (${wordCount}/250 words). Unable to fully address all parts of prompt.`);
            } else {
                taScore = 4.0;
                taFeedback.push(`Severely underdeveloped (${wordCount}/250 words). Ideas not extended.`);
            }
        }

        // Paragraph structural impact on TA & CC
        if (paragraphs.length === 1) {
            taScore = Math.min(taScore, 5.0);
            taFeedback.push("Writing is in a single unbroken block. Standard IELTS requires distinct paragraphs.");
        } else if (paragraphs.length >= 3 && paragraphs.length <= 5) {
            taScore = Math.min(9.0, taScore + 0.5);
            taFeedback.push(`Good essay structure: ${paragraphs.length} distinct paragraphs.`);
        }

        // Overview / Conclusion check (Task 1 needs Overview, Task 2 needs Conclusion)
        const lowerText = cleaned.toLowerCase();
        if (taskNum === 1) {
            const hasOverview = /overall|in summary|it is evident|it can be seen|the trend illustrates/i.test(lowerText);
            if (hasOverview) {
                taScore = Math.min(9.0, taScore + 0.5);
                taFeedback.push("Clear overview sentence/paragraph detected (critical for Band 7+).");
            } else {
                taScore = Math.min(taScore, 6.0);
                taFeedback.push("No clear 'Overall' overview detected. Task 1 requires an overview to exceed Band 6.");
            }
        } else {
            const hasConclusion = /in conclusion|to conclude|to sum up|in summary|all in all/i.test(lowerText);
            if (hasConclusion) {
                taScore = Math.min(9.0, taScore + 0.5);
                taFeedback.push("Clear concluding paragraph detected.");
            } else {
                taScore = Math.min(taScore, 6.0);
                taFeedback.push("Missing an explicit conclusion. Always end with 'In conclusion, ...'");
            }
        }

        // --- B. COHERENCE & COHESION (CC) ---
        let ccScore = 5.5;
        const ccFeedback = [];
        const cohesiveFound = [];

        // Match cohesive devices
        for (const phrase of ALL_COHESIVE_PHRASES) {
            const regex = new RegExp(`\\b${phrase}\\b`, "gi");
            const matches = lowerText.match(regex);
            if (matches && matches.length > 0) {
                cohesiveFound.push({ phrase: phrase, count: matches.length });
            }
        }

        const uniqueCohesiveCount = cohesiveFound.length;
        const totalCohesiveHits = cohesiveFound.reduce((sum, item) => sum + item.count, 0);

        if (uniqueCohesiveCount >= 8) {
            ccScore = 7.5;
            ccFeedback.push(`Wide range of linking devices used (${uniqueCohesiveCount} varied cohesive phrases).`);
        } else if (uniqueCohesiveCount >= 5) {
            ccScore = 6.5;
            ccFeedback.push(`Good linking devices present (${uniqueCohesiveCount} varied transitions).`);
        } else if (uniqueCohesiveCount >= 3) {
            ccScore = 6.0;
            ccFeedback.push(`Basic cohesive devices detected (${uniqueCohesiveCount} transitions).`);
        } else if (uniqueCohesiveCount >= 1) {
            ccScore = 5.0;
            ccFeedback.push(`Limited cohesive devices (${uniqueCohesiveCount} found). Ideas appear loosely connected.`);
        } else {
            ccScore = 4.0;
            ccFeedback.push("Very few cohesive devices detected. Sentences do not flow naturally.");
        }

        // Check paragraphing balance
        if (paragraphs.length >= 3) {
            const paraLengths = paragraphs.map(p => extractWords(p).length);
            const minPara = Math.min(...paraLengths);
            if (minPara < 15) {
                ccScore = Math.max(4.0, ccScore - 0.5);
                ccFeedback.push("At least one paragraph is too brief (< 15 words). Develop each point more fully.");
            }
        } else if (paragraphs.length < 2) {
            ccScore = Math.min(ccScore, 5.0);
            ccFeedback.push("Lack of paragraphing severely harms coherence. Group ideas into 3-5 distinct paragraphs.");
        }

        // --- C. LEXICAL RESOURCE (LR) ---
        let lrScore = 5.5;
        const lrFeedback = [];

        // 1. Vocabulary Diversity: Type-Token Ratio (unique words / total words)
        const wordFreq = {};
        const lowerWords = words.map(w => w.toLowerCase());
        for (const w of lowerWords) {
            wordFreq[w] = (wordFreq[w] || 0) + 1;
        }

        const uniqueWords = Object.keys(wordFreq).length;
        const ttr = wordCount > 0 ? (uniqueWords / wordCount) : 0;

        // 2. Academic Vocabulary Density
        const academicWordsFound = [];
        for (const w of lowerWords) {
            if (ACADEMIC_WORDS.has(w) && !academicWordsFound.includes(w)) {
                academicWordsFound.push(w);
            }
        }
        const academicDensity = wordCount > 0 ? ((academicWordsFound.length / wordCount) * 100) : 0;

        // 3. Word Repetition Warning
        const overusedWords = [];
        for (const [w, count] of Object.entries(wordFreq)) {
            if (count >= 5 && !STOP_WORDS.has(w) && w.length > 3) {
                overusedWords.push({ word: w, count: count });
            }
        }

        // Score Calculation for LR
        if (academicDensity >= 7.0 && ttr >= 0.50) {
            lrScore = 7.5;
            lrFeedback.push(`Rich, varied academic vocabulary (${academicWordsFound.length} AWL words, ${academicDensity.toFixed(1)}% density).`);
        } else if (academicDensity >= 4.5 && ttr >= 0.42) {
            lrScore = 6.5;
            lrFeedback.push(`Solid academic vocabulary (${academicWordsFound.length} AWL words detected).`);
        } else if (academicDensity >= 2.5) {
            lrScore = 6.0;
            lrFeedback.push(`Satisfactory vocabulary range, but contains common everyday phrasing.`);
        } else {
            lrScore = 5.0;
            lrFeedback.push(`Limited vocabulary range (${academicWordsFound.length} academic terms). Try using more formal synonyms.`);
        }

        if (overusedWords.length > 0) {
            lrScore = Math.max(4.5, lrScore - 0.5);
            const wordListStr = overusedWords.slice(0, 3).map(o => `"${o.word}" (${o.count}x)`).join(", ");
            lrFeedback.push(`Repetition detected on: ${wordListStr}. Use synonyms to demonstrate lexical range.`);
        }

        // --- D. GRAMMATICAL RANGE & ACCURACY (GRA) ---
        let graScore = 5.5;
        const graFeedback = [];

        const sentenceCount = sentences.length;
        const avgSentenceLength = sentenceCount > 0 ? (wordCount / sentenceCount) : 0;

        // Count complex sentence markers
        let complexSentences = 0;
        for (const s of sentences) {
            const sLower = s.toLowerCase();
            const hasMarker = COMPLEX_SENTENCE_MARKERS.some(m => new RegExp(`\\b${m}\\b`, "i").test(sLower));
            if (hasMarker) complexSentences++;
        }
        const complexRatio = sentenceCount > 0 ? (complexSentences / sentenceCount) : 0;

        // Sentence length variety
        if (avgSentenceLength >= 15 && avgSentenceLength <= 26 && complexRatio >= 0.40) {
            graScore = 7.0;
            graFeedback.push(`Strong sentence variety and complexity (${complexSentences} complex/compound sentences, ~${avgSentenceLength.toFixed(0)} words/sentence).`);
        } else if (avgSentenceLength >= 12 && avgSentenceLength <= 30 && complexRatio >= 0.25) {
            graScore = 6.5;
            graFeedback.push(`Good mix of simple and complex sentence structures (${complexSentences} complex clauses).`);
        } else if (avgSentenceLength < 10) {
            graScore = 5.0;
            graFeedback.push(`Sentences are very short and simple (average ${avgSentenceLength.toFixed(0)} words). Aim for compound sentences.`);
        } else if (avgSentenceLength > 35) {
            graScore = 5.0;
            graFeedback.push(`Run-on sentences detected (average ${avgSentenceLength.toFixed(0)} words). Break overly long sentences into punchier units.`);
        } else {
            graScore = 6.0;
            graFeedback.push(`Standard grammatical structures used. Adding more conditional or relative clauses will boost your score.`);
        }

        // Clamp individual sub-scores between 5.0 and 7.0
        const finalTA = Math.max(5.0, Math.min(7.0, roundToIELTSHalfBand(taScore)));
        const finalCC = Math.max(5.0, Math.min(7.0, roundToIELTSHalfBand(ccScore)));
        const finalLR = Math.max(5.0, Math.min(7.0, roundToIELTSHalfBand(lrScore)));
        const finalGRA = Math.max(5.0, Math.min(7.0, roundToIELTSHalfBand(graScore)));

        // Task Average = arithmetic mean of 4 criteria rounded to IELTS 0.5 band (clamped between 5.0 and 7.0)
        const rawAvg = (finalTA + finalCC + finalLR + finalGRA) / 4;
        const finalTaskBand = Math.max(5.0, Math.min(7.0, roundToIELTSHalfBand(rawAvg)));

        return {
            taskNumber: taskNum,
            wordCount: wordCount,
            targetWords: targetWords,
            isUnderlength: wordCount < targetWords,
            paragraphCount: paragraphs.length,
            sentenceCount: sentenceCount,
            scores: {
                taskAchievement: finalTA,
                coherenceCohesion: finalCC,
                lexicalResource: finalLR,
                grammaticalRange: finalGRA,
                taskAverage: finalTaskBand
            },
            diagnostics: {
                ttr: Number(ttr.toFixed(2)),
                academicDensity: Number(academicDensity.toFixed(1)),
                academicWordsFound: academicWordsFound.slice(0, 15),
                cohesiveDevicesFound: cohesiveFound,
                repeatedWords: overusedWords,
                avgSentenceLength: Number(avgSentenceLength.toFixed(1)),
                complexSentenceCount: complexSentences
            },
            feedback: {
                ta: taFeedback,
                cc: ccFeedback,
                lr: lrFeedback,
                gra: graFeedback
            }
        };
    }

    /**
     * Analyzes full Writing exam (combining Task 1 and Task 2).
     * Formula: Overall Band = (Task 1 * 1/3) + (Task 2 * 2/3) rounded to nearest 0.5 band.
     * @param {string} task1Text
     * @param {string} task2Text
     * @returns {Object} Overall band, individual task evaluations, and aggregate diagnostics
     */
    function analyzeWritingExam(task1Text, task2Text) {
        const t1Result = analyzeTask(task1Text, 1);
        const t2Result = analyzeTask(task2Text, 2);

        let overallBand = 0.0;
        if (t1Result.wordCount > 0 && t2Result.wordCount > 0) {
            const weightedScore = (t1Result.scores.taskAverage * (1 / 3)) + (t2Result.scores.taskAverage * (2 / 3));
            overallBand = Math.max(5.0, Math.min(7.0, roundToIELTSHalfBand(weightedScore)));
        } else if (t2Result.wordCount > 0) {
            overallBand = Math.max(5.0, Math.min(7.0, roundToIELTSHalfBand(t2Result.scores.taskAverage * 0.7))); // Penalized for missing Task 1
        } else if (t1Result.wordCount > 0) {
            overallBand = Math.max(5.0, Math.min(7.0, roundToIELTSHalfBand(t1Result.scores.taskAverage * 0.35))); // Penalized for missing Task 2
        }

        return {
            overallBand: overallBand,
            task1: t1Result,
            task2: t2Result,
            totalWords: t1Result.wordCount + t2Result.wordCount,
            bothSubmitted: t1Result.wordCount > 0 && t2Result.wordCount > 0
        };
    }

    // --------------------------------------------------------------------------
    // 4. UI RENDERER FOR RESULT & REVIEW PAGES
    // --------------------------------------------------------------------------

    function renderDiagnosticBadge(score) {
        const bg = score >= 7.0 ? "bg-emerald-600" : score >= 6.0 ? "bg-indigo-600" : score >= 5.0 ? "bg-amber-500" : "bg-rose-500";
        return `<span class="inline-flex items-center justify-center px-2.5 py-0.5 rounded-full text-white text-xs font-bold ${bg}">Band ${score.toFixed(1)}</span>`;
    }

    function renderProgressBar(score) {
        const pct = Math.min(100, (score / 9.0) * 100);
        const color = score >= 7.0 ? "bg-emerald-500" : score >= 6.0 ? "bg-indigo-500" : score >= 5.0 ? "bg-amber-500" : "bg-rose-500";
        return `
            <div class="w-full bg-slate-200 dark:bg-zinc-700 h-2 rounded-full overflow-hidden mt-1.5">
                <div class="${color} h-2 rounded-full transition-all duration-500" style="width: ${pct}%;"></div>
            </div>
        `;
    }

    function buildTaskAnalysisHTML(taskResult) {
        const t = taskResult;
        const s = t.scores;
        const d = t.diagnostics;

        const lengthBadge = t.isUnderlength
            ? `<span class="text-rose-600 dark:text-rose-400 font-bold">⚠️ ${t.wordCount}/${t.targetWords} words (Under length)</span>`
            : `<span class="text-emerald-600 dark:text-emerald-400 font-bold">✓ ${t.wordCount} words (Target met)</span>`;

        // Render academic words chips
        const awlChips = d.academicWordsFound.length > 0
            ? d.academicWordsFound.slice(0, 10).map(w => `<span class="inline-block px-2 py-0.5 rounded text-[11px] font-mono bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">${w}</span>`).join(" ")
            : `<em class="text-slate-400 text-xs">No formal academic vocabulary detected.</em>`;

        // Render cohesive chips
        const cohesiveChips = d.cohesiveDevicesFound.length > 0
            ? d.cohesiveDevicesFound.slice(0, 8).map(c => `<span class="inline-block px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">${c.phrase} <small class="text-emerald-500">(${c.count}x)</small></span>`).join(" ")
            : `<em class="text-slate-400 text-xs">Few cohesive devices detected.</em>`;

        return `
            <div class="mt-4 p-5 rounded-xl border border-indigo-100 dark:border-zinc-700 bg-white dark:bg-zinc-850 shadow-sm space-y-4">
                <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 dark:border-zinc-700/80 pb-3">
                    <div class="flex items-center gap-2">
                        <span class="text-base font-bold text-slate-900 dark:text-white">⚡ Automated IELTS Analyzer &bull; Task ${t.taskNumber}</span>
                        ${renderDiagnosticBadge(s.taskAverage)}
                    </div>
                    <div class="text-xs">
                        ${lengthBadge}
                    </div>
                </div>

                <!-- 4 Criteria Score Grid -->
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                    <div class="p-3 rounded-lg bg-slate-50 dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700">
                        <div class="flex items-center justify-between">
                            <span class="text-slate-500 text-[11px] font-medium">${t.taskNumber === 1 ? 'Task Achievement' : 'Task Response'}</span>
                            <strong class="text-slate-800 dark:text-white text-sm">${s.taskAchievement.toFixed(1)}</strong>
                        </div>
                        ${renderProgressBar(s.taskAchievement)}
                    </div>
                    <div class="p-3 rounded-lg bg-slate-50 dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700">
                        <div class="flex items-center justify-between">
                            <span class="text-slate-500 text-[11px] font-medium">Coherence &amp; Cohesion</span>
                            <strong class="text-slate-800 dark:text-white text-sm">${s.coherenceCohesion.toFixed(1)}</strong>
                        </div>
                        ${renderProgressBar(s.coherenceCohesion)}
                    </div>
                    <div class="p-3 rounded-lg bg-slate-50 dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700">
                        <div class="flex items-center justify-between">
                            <span class="text-slate-500 text-[11px] font-medium">Lexical Resource</span>
                            <strong class="text-slate-800 dark:text-white text-sm">${s.lexicalResource.toFixed(1)}</strong>
                        </div>
                        ${renderProgressBar(s.lexicalResource)}
                    </div>
                    <div class="p-3 rounded-lg bg-slate-50 dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700">
                        <div class="flex items-center justify-between">
                            <span class="text-slate-500 text-[11px] font-medium">Grammar &amp; Accuracy</span>
                            <strong class="text-slate-800 dark:text-white text-sm">${s.grammaticalRange.toFixed(1)}</strong>
                        </div>
                        ${renderProgressBar(s.grammaticalRange)}
                    </div>
                </div>

                <!-- Structural Insights -->
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs pt-1">
                    <div class="p-3 rounded-lg bg-indigo-50/40 dark:bg-indigo-950/20 border border-indigo-100 dark:border-indigo-900/40">
                        <span class="font-bold text-indigo-900 dark:text-indigo-200 block mb-1">🔗 Cohesion &amp; Discourse Markers:</span>
                        <div class="flex flex-wrap gap-1 mt-1.5">${cohesiveChips}</div>
                    </div>
                    <div class="p-3 rounded-lg bg-purple-50/40 dark:bg-purple-950/20 border border-purple-100 dark:border-purple-900/40">
                        <span class="font-bold text-purple-900 dark:text-purple-200 block mb-1">📚 Academic Vocabulary Highlights:</span>
                        <div class="flex flex-wrap gap-1 mt-1.5">${awlChips}</div>
                    </div>
                </div>

                <!-- Diagnostic Key Takeaways -->
                <div class="p-3 rounded-lg bg-slate-50 dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700 text-xs space-y-1.5">
                    <div class="font-bold text-slate-800 dark:text-white flex items-center gap-1.5">
                        <span>💡 Examiner Diagnostic Insights:</span>
                    </div>
                    <ul class="list-disc list-inside space-y-1 text-slate-600 dark:text-slate-300">
                        ${[...t.feedback.ta, ...t.feedback.cc, ...t.feedback.lr, ...t.feedback.gra].map(f => `<li>${f}</li>`).join("")}
                    </ul>
                </div>
            </div>
        `;
    }

    // Export module to global scope
    window.IELTSWritingAnalyzer = {
        cleanText: cleanText,
        extractWords: extractWords,
        extractSentences: extractSentences,
        extractParagraphs: extractParagraphs,
        roundToIELTSHalfBand: roundToIELTSHalfBand,
        analyzeTask: analyzeTask,
        analyzeWritingExam: analyzeWritingExam,
        buildTaskAnalysisHTML: buildTaskAnalysisHTML
    };

})(typeof window !== "undefined" ? window : this);

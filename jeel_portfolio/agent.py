"""Small local grammar + Gemini fallback, each routed through guarded tools."""

import os
import re
import time
import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from .cache import AnswerCache
from .common_questions import plan_common_question
from .database import Database, DataError, ROOT
from .exposure import calculate_exposure, name_in_question
from .planner import GeminiPlanner, Plan, ProviderUnavailable


def _contains(text: str, *terms: str) -> bool:
    return any(term in text for term in terms)


class PortfolioAgent:
    def __init__(self, root: Path = ROOT, cache: bool = True, model: str | None = None):
        self.root = Path(root)
        load_dotenv(self.root / ".env", override=False)
        self.db = Database(self.root)
        self.symbols = tuple(row[0] for row in self.db.query("SELECT symbol FROM securities").rows)
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        implementation = hashlib.sha256()
        for filename in ("agent.py", "common_questions.py", "database.py", "exposure.py", "planner.py"):
            implementation.update((Path(__file__).parent / filename).read_bytes())
        version = self.db.fingerprint + ":" + implementation.hexdigest()
        self.cache = AnswerCache(self.root / ".cache" / "answers.sqlite3", version, self.model) if cache else None
        self.planner = GeminiPlanner(self.model)

    def _fast_plan(self, question: str) -> Plan | None:
        q = " ".join(re.findall(r"[a-z0-9]+", question.casefold()))
        common = plan_common_question(question, self.db)
        if common:
            return common
        name = name_in_question(question, self.db.portfolios)
        modifiers = q.replace("assets under management", "aum")
        aum_q = q.replace("assets under management aum", "aum").replace("assets under management", "aum")
        dated_aum = re.fullmatch(
            r"(?:what is (?:the )?)?(?:total|sum of) aum for (?:(active|passive) )?"
            r"(?:(high|medium|low) risk portfolios|portfolios with (high|medium|low) target risk level) "
            r"(?:created|with creation date) (after|before|since) ((?:19|20)\d{2}) (\d{1,2}) (\d{1,2})",
            aum_q,
        )
        if dated_aum:
            status, first_risk, second_risk, relation, year, month, day = dated_aum.groups()
            try:
                cutoff = date(int(year), int(month), int(day)).isoformat()
            except ValueError:
                return None
            operator = {"after": ">", "before": "<", "since": ">="}[relation]
            sql = f"SELECT SUM(total_aum) AS total_aum FROM portfolios WHERE lower(target_risk_level)=:risk AND creation_date {operator} :cutoff"
            params = [{"name": "risk", "value": first_risk or second_risk}, {"name": "cutoff", "value": cutoff}]
            if status:
                sql += " AND lower(status)=:status"
                params.append({"name": "status", "value": status})
            return Plan(tool="sql", sql=sql, parameters=params)
        if re.search(r"\b(as of|after|before|since|purchased|created|less than|greater than|above|below|at least|at most|during|last year|this year)\b", q) or re.search(r"\b(?:19|20)\d{2}\b", q):
            return None
        if re.search(r"\b(over|under|country|currency|usd)\b", modifiers):
            return None
        if _contains(q, " not ", " outside ", " excluding ", " except ", " without "):
            return None
        # Only route patterns whose filters and metric have a deterministic meaning.
        if name:
            aliases = {name.casefold(), re.sub(r" (?:fund|portfolio)$", "", name.casefold())}
            exposure_phrases = set()
            for alias in aliases:
                for named in (alias, "the " + alias):
                    exposure_phrases.update((
                        f"what are the sector exposures for {named}",
                        f"what is the sector exposure for {named}",
                        f"calculate the sector exposure breakdown for {named}",
                        f"show the sector allocation for {named}",
                        f"what is the stock sector exposure of {named}",
                        f"what is the equity normalized sector exposure for {named}",
                    ))
            if q in exposure_phrases:
                return Plan(tool="exposure", portfolio_name=name,
                            basis="equity" if "equity normalized" in q else "portfolio")
        hybrid_match = re.fullmatch(r"(?:which|what) (?:(active|passive) )?(?:(high|medium|low) risk )?portfolios? (?:has|have) the (?:highest|greatest) [a-z ]+ exposure", q)
        if hybrid_match:
            sector = next((s for s in self.db.sectors if s.casefold() in q), None)
            if sector:
                clauses, params = [], []
                if hybrid_match.group(1) == "active":
                    clauses.append("status=:status")
                    params.append({"name":"status","value":"Active"})
                elif hybrid_match.group(1) == "passive":
                    clauses.append("status=:status")
                    params.append({"name":"status","value":"Passive"})
                risk = hybrid_match.group(2)
                if risk:
                    clauses.append("lower(target_risk_level)=:risk")
                    params.append({"name":"risk","value":risk})
                sql = "SELECT portfolio_name FROM portfolios" + (" WHERE " + " AND ".join(clauses) if clauses else "")
                return Plan(tool="hybrid", sql=sql, parameters=params, sector=sector, top_n=1)
        count_match = re.fullmatch(r"(?:how many|count|number of) (?:(active|passive) )?(?:(high|medium|low)(?: target)? risk )?portfolios(?: do we have)?(?: in total)?", q)
        if count_match:
            clauses, params = [], []
            if count_match.group(1):
                clauses.append("lower(status)=:status")
                params.append({"name":"status","value":count_match.group(1)})
            if count_match.group(2):
                clauses.append("lower(target_risk_level)=:risk")
                params.append({"name":"risk","value":count_match.group(2)})
            sql = "SELECT COUNT(*) AS portfolio_count FROM portfolios" + (" WHERE " + " AND ".join(clauses) if clauses else "")
            return Plan(tool="sql", sql=sql, parameters=params)
        if re.fullmatch(r"(?:what are the names of all active portfolios|list active portfolio names|show active portfolio names)", q):
            return Plan(tool="sql", sql="SELECT portfolio_name FROM portfolios WHERE status = :status ORDER BY portfolio_name", parameters=[{"name":"status","value":"Active"}])
        aum_match = re.fullmatch(r"(?:what is (?:the )?)?(?:total|sum of) aum for (?:(active|passive) )?(?:portfolios with (high|medium|low) target risk level|(high|medium|low) risk portfolios)", aum_q)
        if aum_match:
            status = aum_match.group(1)
            level = aum_match.group(2) or aum_match.group(3)
            sql = "SELECT SUM(total_aum) AS total_aum FROM portfolios WHERE lower(target_risk_level) = :risk"
            params = [{"name":"risk","value":level}]
            if status:
                sql += " AND lower(status)=:status"
                params.append({"name":"status","value":status})
            return Plan(tool="sql", sql=sql, parameters=params)
        if re.fullmatch(r"(?:which securities are in|list securities in) (?:the )?[a-z ]+ sector", q):
            sector = next((s for s in self.db.sectors if s.casefold() in q), None)
            if sector and q.endswith(sector.casefold() + " sector"):
                return Plan(tool="sql", sql="SELECT s.symbol, s.company_name FROM securities s JOIN sectors sec ON sec.sector_id=s.sector_id WHERE sec.sector_name=:sector ORDER BY s.symbol", parameters=[{"name":"sector","value":sector}])
        if re.fullmatch(r"(?:what is the )?average current price of securities (?:in each|by) sector", q):
            return Plan(tool="sql", sql="SELECT sec.sector_name, AVG(s.current_price) AS avg_price FROM securities s JOIN sectors sec ON sec.sector_id=s.sector_id GROUP BY sec.sector_name ORDER BY avg_price DESC")
        if name and re.fullmatch(rf"(?:show me the |the |)top \d+ holdings by cost basis in (?:the )?{re.escape(name.casefold())}", q):
            top = re.search(r"\btop (\d+)\b", q)
            n = min(int(top.group(1)), 100) if top else 5
            return Plan(tool="sql", sql="SELECT h.holding_id, s.symbol, s.company_name, h.quantity, h.cost_basis FROM holdings h JOIN securities s ON s.security_id=h.security_id JOIN portfolios p ON p.portfolio_id=h.portfolio_id WHERE p.portfolio_name=:name ORDER BY h.cost_basis DESC LIMIT :n", parameters=[{"name":"name","value":name},{"name":"n","value":n}])
        if re.fullmatch(r"for each portfolio show the total value of [a-z ]+ sector holdings and what percentage it represents of the total portfolio value", q):
            sector = next((s for s in self.db.sectors if s.casefold() in q), None)
            if sector and f"value of {sector.casefold()} sector holdings" in q:
                return Plan(tool="sql", sql="""WITH sector_value AS (SELECT p.portfolio_id,p.portfolio_name,SUM(h.quantity*s.current_price) AS sector_value FROM portfolios p JOIN holdings h USING(portfolio_id) JOIN securities s USING(security_id) JOIN sectors sec USING(sector_id) WHERE sec.sector_name=:sector GROUP BY p.portfolio_id), total_value AS (SELECT p.portfolio_id,SUM(h.quantity*s.current_price) AS total_value FROM portfolios p JOIN holdings h USING(portfolio_id) JOIN securities s USING(security_id) GROUP BY p.portfolio_id) SELECT sv.portfolio_name,sv.sector_value,tv.total_value,ROUND(100.0*sv.sector_value/NULLIF(tv.total_value,0),2) AS sector_percentage FROM sector_value sv JOIN total_value tv USING(portfolio_id) ORDER BY sector_percentage DESC""", parameters=[{"name":"sector","value":sector}])
        if re.fullmatch(r"find portfolios that have holdings in (?:more than|over) \d+ different sectors and show their diversification metrics", q):
            match = re.search(r"(?:more than|over) (\d+)", q)
            if match:
                return Plan(tool="sql", sql="""WITH sector_count AS (SELECT p.portfolio_id,p.portfolio_name,COUNT(DISTINCT sec.sector_id) AS sector_count FROM portfolios p JOIN holdings h USING(portfolio_id) JOIN securities s USING(security_id) JOIN sectors sec USING(sector_id) WHERE s.asset_type='Stock' GROUP BY p.portfolio_id HAVING COUNT(DISTINCT sec.sector_id)>:minimum), holding_count AS (SELECT portfolio_id,COUNT(*) AS total_holdings FROM holdings GROUP BY portfolio_id) SELECT sc.portfolio_name,sc.sector_count,hc.total_holdings,ROUND(CAST(sc.sector_count AS REAL)/hc.total_holdings,3) AS diversification_ratio FROM sector_count sc JOIN holding_count hc USING(portfolio_id) ORDER BY diversification_ratio DESC""", parameters=[{"name":"minimum","value":int(match.group(1))}])
        return None

    def answer(self, question: str, force_gemini: bool = False) -> dict:
        started = time.perf_counter_ns()
        question = question.strip()
        if not question or len(question) > 1000:
            return {"status":"error","message":"Enter a question of 1–1000 characters.","error_code":"invalid_question","elapsed_ms":0}
        glossary = self._glossary_definition(question)
        if glossary:
            term, definition = glossary
            return {"question":question,"status":"ok","message":definition,"tool":"glossary",
                    "route":"local_glossary","columns":["term","definition"],
                    "rows":[[term,definition]],"warnings":[],
                    "evidence":{"source":"Local definitions of the supplied portfolio snapshot"},
                    "cache_status":"not_applicable",
                    "elapsed_ms":round((time.perf_counter_ns()-started)/1e6,6)}
        scope_message = self._scope_message(question)
        if scope_message:
            return {"question":question,"status":"clarify","message":scope_message,
                    "route":"scope_guard","tool":None,"cache_status":"not_applicable",
                    "elapsed_ms":round((time.perf_counter_ns()-started)/1e6,6)}
        if self.cache and not force_gemini:
            hit = self.cache.get(question)
            if hit:
                result, level = hit
                return {**result,"route":"cache","cache_status":level,"elapsed_ms":round((time.perf_counter_ns()-started)/1e6,6)}
        try:
            plan = None if force_gemini else self._fast_plan(question)
            route = "fast" if plan else "gemini"
            if plan is None:
                plan = self.planner.plan(question, self.db)
            if route == "gemini" and plan.tool == "hybrid" and _contains(question.casefold(), "total value", "market value", "quantity", "current price"):
                plan = self.planner.plan(question, self.db, "Hybrid is only for weight-based sector exposure. This question asks for market value; choose sql and preserve all holdings in the total-value denominator.")
                if plan.tool != "sql":
                    raise DataError("Gemini did not produce the required market-value SQL plan.")
            if plan.tool == "clarify":
                result = {"status":"clarify","message":plan.clarification or "Please clarify the portfolio or metric.","tool":None,"route":route}
            elif plan.tool == "exposure":
                exposure = calculate_exposure(self.db, plan.portfolio_name, plan.basis)
                result = {"status":"ok","message":f"Stock sector exposures for {exposure['portfolio_name']} (% of {plan.basis}).","tool":"exposure_calculator","route":route+"_exposure","columns":exposure["columns"],"rows":exposure["rows"],"warnings":exposure["warnings"],"evidence":{"portfolio":exposure["portfolio_name"],"basis":plan.basis,"formula":exposure["formula"],"equity_weight_pct":exposure["equity_weight_pct"],"bond_weight_pct":exposure["bond_weight_pct"],"contributions":exposure["contributions"]}}
            elif plan.tool == "hybrid":
                def select_cohort(candidate):
                    bound = {item.name:item.value for item in candidate.parameters}
                    selected = self.db.query(candidate.sql, bound)
                    if selected.truncated or tuple(col.casefold() for col in selected.columns) != ("portfolio_name",):
                        raise DataError("Hybrid SQL must return one complete portfolio_name column.")
                    if any(len(row) != 1 or row[0] not in self.db.portfolios for row in selected.rows):
                        raise DataError("Hybrid SQL returned a portfolio outside the supplied snapshot.")
                    sector_name = next((name for name in self.db.sectors if name.casefold() == candidate.sector.casefold()), None)
                    if not sector_name:
                        raise DataError("Hybrid comparison needs one recorded sector name.")
                    return selected, bound, sector_name
                try:
                    cohort, params, sector = select_cohort(plan)
                except DataError as exc:
                    if route != "gemini":
                        raise
                    plan = self.planner.plan(question, self.db, str(exc))
                    if plan.tool != "hybrid":
                        raise DataError("Hybrid plan correction changed the requested tool.")
                    cohort, params, sector = select_cohort(plan)
                rows, details = [], []
                for (portfolio_name,) in dict.fromkeys(cohort.rows):
                    exposure = calculate_exposure(self.db, portfolio_name, plan.basis)
                    pct = next((row[1] for row in exposure["rows"] if row[0] == sector), 0.0)
                    rows.append([portfolio_name, pct])
                    details.append({"portfolio":portfolio_name,"contributions":[item for item in exposure["contributions"] if item["sector"] == sector]})
                rows.sort(key=lambda row: (-row[1], row[0]))
                comparison_rows = [row[:] for row in rows]
                if plan.top_n > 0:
                    rows = rows[:plan.top_n]
                if plan.top_n == 1 and rows:
                    tied = len(comparison_rows) > 1 and comparison_rows[1][1] == rows[0][1]
                    standing = "is tied for the highest" if tied else "has the highest"
                    message = f"{rows[0][0]} {standing} {sector} exposure at {rows[0][1]:g}%."
                elif comparison_rows:
                    message = f"Compared {sector} exposure across {len(comparison_rows)} portfolios."
                else:
                    message = f"No portfolios matched the requested {sector} exposure comparison."
                result = {"status":"ok","message":message,"tool":"hybrid","route":route+"_hybrid","columns":["portfolio_name","exposure_pct"],"rows":rows,"warnings":[],"evidence":{"cohort_sql":plan.sql,"parameters":params,"sector":sector,"basis":plan.basis,"cohort_size":len(cohort.rows),"comparison_rows":comparison_rows,"contributions":details}}
            else:
                params = {item.name:item.value for item in plan.parameters}
                try:
                    self._validate_sql_plan(question, plan.sql)
                    table = self.db.query(plan.sql, params)
                    self._validate_result(question, table)
                except DataError as exc:
                    if route != "gemini":
                        raise
                    plan = self.planner.plan(question, self.db, str(exc))
                    if plan.tool != "sql":
                        raise DataError("The revised plan did not provide a SQL query.")
                    params = {item.name:item.value for item in plan.parameters}
                    self._validate_sql_plan(question, plan.sql)
                    table = self.db.query(plan.sql, params)
                    self._validate_result(question, table)
                if len(table.rows) == 1 and len(table.columns) == 1:
                    value = table.rows[0][0]
                    display = format(Decimal(str(value)), ",f").rstrip("0").rstrip(".") if isinstance(value, float) else str(value)
                    label = table.columns[0].replace("_", " ").capitalize().replace("Aum", "AUM")
                    message = f"{label}: {display}"
                else:
                    message = f"Found {len(table.rows)} row(s)"+(" (truncated)." if table.truncated else ".")
                result = {"status":"ok","message":message,"tool":"sql_query","route":route+"_sql","columns":list(table.columns),"rows":[list(row) for row in table.rows],"warnings":["Result limited to 500 rows."] if table.truncated else [],"evidence":{"sql":plan.sql,"parameters":params}}
            result["question"] = question
            result["cache_status"] = "miss" if self.cache else "disabled"
            result["elapsed_ms"] = round((time.perf_counter_ns()-started)/1e6,6)
            if result["status"] == "ok" and self.cache:
                self.cache.put(question, result)
            return result
        except DataError as exc:
            result = {"question":question,"status":"error","message":str(exc),"error_code":"provider_unavailable" if isinstance(exc, ProviderUnavailable) else "tool_error","route":"error","elapsed_ms":round((time.perf_counter_ns()-started)/1e6,6)}
            if isinstance(exc, ProviderUnavailable):
                result["provider_reason"] = exc.reason
            return result

    @staticmethod
    def _glossary_definition(question: str) -> tuple[str, str] | None:
        """Answer exact term-definition requests without sending them to Gemini."""
        definitions = {
            "portfolio": "A portfolio is a group of investments managed together. In this exercise, each named portfolio has holdings, a target risk level, and recorded AUM.",
            "investment portfolio": "An investment portfolio is a group of assets, such as stocks and bonds, managed together. Here, each portfolio is a named set of recorded holdings.",
            "holding": "A holding is one security position inside a portfolio. The supplied data records its quantity, cost basis, and current weight.",
            "aum": "AUM means Assets Under Management: the total amount recorded for a portfolio. This exercise uses portfolios.total_aum, not a sum rebuilt from quantity and price.",
            "assets under management": "Assets Under Management (AUM) is the total amount recorded for a portfolio. This exercise reads portfolios.total_aum directly.",
            "sector": "A sector groups companies by business activity, such as Technology. The supplied securities are linked to recorded sector categories.",
            "sector exposure": "Sector exposure is the share of a portfolio allocated to a sector. Here it uses recorded stock holding weights; bonds are excluded from stock-sector exposure.",
            "cost basis": "Cost basis is the recorded purchase cost of a holding in the supplied data. It is separate from current market value.",
            "risk level": "Target risk level is the portfolio's recorded High, Medium, or Low label. It describes the supplied classification, not a prediction of future losses.",
            "diversification": "Diversification describes how holdings are spread across sectors or assets. In this exercise, sector counts and holding counts help inspect that spread.",
        }
        q = " ".join(re.findall(r"[a-z0-9]+", question.casefold()))
        terms = "|".join(re.escape(term) for term in sorted(definitions, key=len, reverse=True))
        match = re.fullmatch(
            rf"(?:what is (?:a |an |the )?|what does |define |explain (?:what )?(?:a |an |the )?|tell me what (?:a |an |the )?)"
            rf"({terms})(?: mean| is| in simple terms| in this dataset| in this exercise)?",
            q,
        )
        return (match.group(1), definitions[match.group(1)]) if match else None

    def _scope_message(self, question: str) -> str | None:
        """Reject clearly unsupported requests before spending a model call."""
        q = " ".join(re.findall(r"[a-z0-9]+", question.casefold()))
        if re.search(r"\b(ignore (?:all |the |my )?(?:previous |prior )?instructions|reveal (?:the |your )?(?:api key|secret|system prompt)|delete (?:the |all )?(?:data|database|tables|holdings|portfolios)|drop (?:the )?table)\b", q):
            return "I can only read the supplied portfolio snapshot; I cannot reveal private instructions or change its data."
        if re.search(r"\b(should i (?:buy|sell|invest)|what (?:should|must) i (?:buy|sell)|recommend (?:a |me )?(?:stock|investment)|predict (?:the )?(?:market|price)|guarantee (?:a )?return)\b", q):
            return "I can explain the recorded portfolio figures, but I cannot give investment advice or predict returns."
        if re.search(r"\b(tell me a joke|write (?:me )?a poem|what(?: is| s) the weather|who (?:manages|owns) (?:the )?(?:fund|portfolio))\b", q):
            return "I can answer questions about the supplied portfolios, holdings, AUM, risk, and sector exposure."
        anchor = re.search(
            r"\b(portfolios?|funds?|holdings?|securities|security|sectors?|aum|assets under management|"
            r"stocks?|bonds?|risks?|exposures?|weights?|allocations?|diversification|concentrations?|benchmarks?|"
            r"performance|returns?|transactions?|quantities|quantity|cost basis|prices?|"
            r"market value|currenc(?:y|ies)|exchange|symbols?|dividends?)\b", q,
        )
        named = name_in_question(question, self.db.portfolios)
        named = named or next((sector for sector in self.db.sectors if sector.casefold() in q), None)
        named = named or next((symbol for symbol in self.symbols if re.search(rf"\b{re.escape(symbol.casefold())}\b", q)), None)
        if not anchor and not named:
            if re.search(r"\b(who (?:is|am|are|was)|tell me who|what is my name|do you know me)\b", q):
                return "The supplied portfolio files do not identify people. Ask about a portfolio, holding, AUM, or sector instead."
            return "Please ask about the supplied portfolio snapshot: holdings, AUM, risk, sectors, securities, or performance."
        return None

    @staticmethod
    def _validate_sql_plan(question, sql):
        q = question.casefold()
        asks_about_funds = bool(re.search(r"\b(portfolios?|funds?)\b", q))
        if re.search(r"\b(active|passive)\b", q) and asks_about_funds:
            if not re.search(r"\bstatus\b", sql, re.IGNORECASE):
                raise DataError("Active and Passive classify portfolios.status, not strategy_type. Apply the requested status filter.")
        if asks_about_funds and re.search(r"\b(high|medium|low)[ -]+(?:target[ -]+)?risk\b", q):
            if not re.search(r"\btarget_risk_level\b", sql, re.IGNORECASE):
                raise DataError("Apply the requested portfolio target_risk_level filter.")
        if asks_about_funds and re.search(r"\b(created|creation date)\b", q):
            if not re.search(r"\bcreation_date\b", sql, re.IGNORECASE):
                raise DataError("Apply the requested portfolio creation-date filter using creation_date.")
        if re.search(r"\b(aum|assets under management)\b", q):
            if not re.search(r"\btotal_aum\b", sql, re.IGNORECASE):
                raise DataError("Recorded AUM comes from portfolios.total_aum, not holdings market value.")
        if PortfolioAgent._asks_total_aum(q):
            if not re.search(r"\bsum\s*\(\s*(?:[a-z][a-z0-9_]*\.)?total_aum\s*\)", sql, re.IGNORECASE):
                raise DataError("A total AUM question requires SUM(portfolios.total_aum), not per-fund rows or holding market value.")
            if re.search(r"\b(high|medium|low)\b", q) and "target_risk_level" not in sql.casefold():
                raise DataError("The requested target risk level must filter the total AUM aggregation.")
            if re.search(r"\b(created|creation)\b", q) and re.search(r"\b(after|before|since)\b", q):
                if "creation_date" not in sql.casefold():
                    raise DataError("The requested portfolio creation-date filter must use portfolios.creation_date.")

    @staticmethod
    def _asks_total_aum(q):
        normalized = q.replace("assets under management", "aum")
        return ("aum" in normalized and re.search(r"\b(total|sum|combined)\b", normalized)
                and not re.search(r"\b(for each|per portfolio|by portfolio|breakdown|individual)\b", normalized))

    def _validate_result(self, question, table):
        q = question.casefold()
        # The exact oracle below is valid only for the simple risk/status cohort
        # covered by the local grammar. A new date or other extra filter changes
        # the cohort; comparing it against all high-risk funds would reject a
        # correct Gemini answer.
        simple_aum_plan = self._fast_plan(question) if self._asks_total_aum(q) else None
        if simple_aum_plan is not None and "creation_date" not in simple_aum_plan.sql.casefold():
            normalized = q.replace("assets under management", "aum")
            risk = next((level for level in ("high", "medium", "low") if re.search(rf"\b{level}\b", normalized)), None)
            status = "active" if re.search(r"\bactive\b", normalized) else ("passive" if re.search(r"\bpassive\b", normalized) else None)
            if risk or status:
                clauses, params = [], {}
                if risk:
                    clauses.append("lower(target_risk_level)=:risk")
                    params["risk"] = risk
                if status:
                    clauses.append("lower(status)=:status")
                    params["status"] = status
                expected = self.db.query("SELECT SUM(total_aum) FROM portfolios WHERE " + " AND ".join(clauses), params).rows[0][0]
                actual = table.rows[0][0] if len(table.rows) == 1 and len(table.columns) == 1 else None
                try:
                    matches = (actual is None and expected is None) or (
                        actual is not None and expected is not None and abs(float(actual) - float(expected)) <= 1e-4
                    )
                except (TypeError, ValueError):
                    matches = False
                if len(table.rows) != 1 or len(table.columns) != 1 or not matches:
                    raise DataError("Total AUM must match the sum of recorded portfolio AUM after the requested filters.")
        if "portfolio" in q and "combined recorded weight" in q and "percentage" in q:
            symbols = [row[0] for row in self.db.query("SELECT symbol FROM securities").rows
                       if re.search(rf"\b{re.escape(row[0])}\b", question, re.IGNORECASE)]
            if len(symbols) >= 2:
                placeholders = ",".join(f":s{i}" for i in range(len(symbols)))
                params = {f"s{i}":symbol for i, symbol in enumerate(symbols)}
                params["count"] = len(symbols)
                expected = self.db.query(f"""SELECT p.portfolio_name,ROUND(SUM(h.current_weight)*100,2)
                    FROM portfolios p JOIN holdings h USING(portfolio_id)
                    JOIN securities s USING(security_id)
                    WHERE s.symbol IN ({placeholders})
                    GROUP BY p.portfolio_id HAVING COUNT(DISTINCT s.symbol)=:count""", params)
                if len(table.columns) != 2 or len(table.rows) != len(expected.rows):
                    raise DataError("Combined recorded weight requires portfolios holding every named security and a percentage column.")
                actual = {row[0]:row[1] for row in table.rows}
                if len(actual) != len(table.rows) or any(
                    name not in actual or abs(float(actual[name])-float(pct)) > 1e-4
                    for name, pct in expected.rows
                ):
                    raise DataError("Combined recorded weight must sum the named holding weights, multiply by 100, and include only funds holding every named security.")
        if ("sector" in q and "portfolio" in q and "total value" in q
                and _contains(q, "percentage", "percent")
                and not _contains(q, "including zero", "include zero", "zero exposure")):
            sector = next((name for name in self.db.sectors if name.casefold() in q), None)
            if sector is None:
                return
            if len(table.columns) != 4 or any(len(row) != 4 for row in table.rows):
                raise DataError("Sector market-value breakdown requires portfolio, sector value, total value, and percentage columns.")
            expected = self.db.query("""WITH sector_value AS (
                SELECT p.portfolio_id,p.portfolio_name,SUM(h.quantity*s.current_price) AS amount
                FROM portfolios p JOIN holdings h USING(portfolio_id)
                JOIN securities s USING(security_id) JOIN sectors sec USING(sector_id)
                WHERE sec.sector_name=:sector GROUP BY p.portfolio_id
            ), total_value AS (
                SELECT p.portfolio_id,SUM(h.quantity*s.current_price) AS amount
                FROM portfolios p JOIN holdings h USING(portfolio_id)
                JOIN securities s USING(security_id) GROUP BY p.portfolio_id
            ) SELECT sv.portfolio_name,sv.amount,tv.amount,
                ROUND(100.0*sv.amount/NULLIF(tv.amount,0),2)
                FROM sector_value sv JOIN total_value tv USING(portfolio_id)
                ORDER BY 4 DESC""", {"sector":sector})
            if len(table.rows) != len(expected.rows):
                raise DataError("Sector market-value breakdown must include exactly the portfolios holding the named sector.")
            actual_by_name = {row[0]:row for row in table.rows}
            if len(actual_by_name) != len(table.rows):
                raise DataError("Sector market-value breakdown contains duplicate portfolios.")
            for row in table.rows:
                try:
                    sector_value, total_value, percentage = float(row[1]), float(row[2]), float(row[3])
                except (TypeError, ValueError) as exc:
                    raise DataError("Sector market-value breakdown has nonnumeric values.") from exc
                if sector_value <= 0 or total_value <= 0:
                    raise DataError("Include only portfolios holding the named sector; preserve all holdings in the denominator.")
                if abs(percentage - round(100 * sector_value / total_value, 2)) > 1e-4:
                    raise DataError("Sector percentage must equal sector value divided by total holding value, rounded to two decimals.")
            for name, subtotal, total, percent in expected.rows:
                row = actual_by_name.get(name)
                if row is None or any(abs(float(a) - float(b)) > 1e-4 for a, b in zip(row[1:], (subtotal, total, percent))):
                    raise DataError("Sector market-value breakdown does not match the supplied holdings and prices.")

    def close(self):
        if self.cache:
            self.cache.close()
        if self.planner.client is not None:
            self.planner.client.close()
        self.db.close()

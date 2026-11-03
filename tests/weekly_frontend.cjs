const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
(async()=>{
 const context=vm.createContext({Date,URL,URLSearchParams});
 const library=new vm.SourceTextModule(fs.readFileSync('static/js/space/library_model.js','utf8'),{context});await library.link(()=>{});await library.evaluate();
 const module=new vm.SourceTextModule(fs.readFileSync('static/js/space/weekly_model.js','utf8'),{context});await module.link(()=>library);await module.evaluate();
 const model=module.namespace.weeklyModel;
 const data={weekly_analysis:{id:1,emotion_trend:{trend:'흐름'},keyword_patterns:JSON.stringify({main_themes:['<script>'],insights:'설명'}),comprehensive_pattern_result:{life_satisfaction:'legacy-invalid-unused'}},diary_analyses:[{date_str:'2026-11-03',scores:[-.4,.6]},{date_str:'2026-11-01',scores:[-.7]}]};
 const result=model(data);assert.equal(result.points[0].date,'2026-11-01');assert.equal(result.points.length,2);assert.equal(result.keyword.main_themes[0],'<script>');
 for(const invalid of ['0.5',null,Infinity,NaN,2]){const copy=structuredClone(data);copy.diary_analyses[0].scores=[invalid];assert.throws(()=>model(copy));}
 const duplicate=structuredClone(data);duplicate.diary_analyses[1].date_str='2026-11-03';assert.throws(()=>model(duplicate));
 const broken=structuredClone(data);broken.weekly_analysis.keyword_patterns='bad';assert.throws(()=>model(broken));
 const js=fs.readFileSync('static/js/space/weekly.js','utf8');assert(!js.includes('innerHTML'));assert(!js.includes('radar'));assert(js.includes('ArrowRight'));assert(js.includes('identity===token()'));
 console.log('PASS weekly: legacy JSON, signed scores, sparse dates, invalid numbers/duplicates, safe text and tab keyboard contract');
})().catch(e=>{console.error(e);process.exitCode=1;});

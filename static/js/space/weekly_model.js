import {emotionPoints} from './library_model.js?v=20261103-7a';
export function object(value){if(typeof value==='string'){try{value=JSON.parse(value);}catch{throw Error('주간 자료의 형식을 확인하지 못했어요.');}}if(!value||typeof value!=='object'||Array.isArray(value))throw Error('주간 자료의 형식을 확인하지 못했어요.');return value;}
export function weeklyModel(data){
 const weekly=object(data?.weekly_analysis),emotion=object(weekly.emotion_trend),keyword=object(weekly.keyword_patterns),overall=object(weekly.comprehensive_pattern_result||{});
 for(const day of data?.diary_analyses||[]){
  for(const key of ['emotions','keywords','keyword_descriptions'])if(day[key]!==undefined&&(!Array.isArray(day[key])||day[key].some(x=>typeof x!=='string')))throw Error('일일 상세 자료를 확인하지 못했어요.');
  if(day.emotions&&day.emotions.length!==day.scores?.length||day.keywords&&day.keyword_descriptions&&day.keywords.length!==day.keyword_descriptions.length||day.summary!==undefined&&typeof day.summary!=='string')throw Error('일일 상세 자료를 확인하지 못했어요.');
 }
 const points=emotionPoints(data);if(!points.length)throw Error('표시할 일일 분석이 없어요.');
 if(new Set(points.map(x=>x.date)).size!==points.length)throw Error('같은 날짜의 분석 자료가 중복되어 있어요.');
 for(const [source,keys]of [[emotion,['trend','dominant_emotion','recommendation']],[keyword,['insights']],[overall,['overall_assessment']]])for(const key of keys)if(source[key]!==undefined&&typeof source[key]!=='string')throw Error('주간 설명 자료를 확인하지 못했어요.');
 for(const key of ['main_themes','trending_keywords','recurring_patterns'])if(keyword[key]!==undefined&&(!Array.isArray(keyword[key])||keyword[key].some(x=>typeof x!=='string')))throw Error('키워드 자료를 확인하지 못했어요.');
 return {weekly,emotion,keyword,overall,points,days:[...data.diary_analyses].sort((a,b)=>a.date_str.localeCompare(b.date_str))};
}

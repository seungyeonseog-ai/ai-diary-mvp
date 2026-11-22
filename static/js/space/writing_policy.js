// 화면 상태와 무관하게 검사할 수 있는 읽기 시간·사진 제한 규칙.
export function replyReadingDelay(text){
 return Math.min(15000,Math.max(5000,[...text].length*65));
}
export const PHOTO_LIMIT=3;

// 표시 문구만 선택한다. 처리 상태와 이동 허용 조건은 writing.js가 유지한다.
export function processingCopy(path='',method='GET'){
 const route=path.split('?')[0];
 if(/\/photos(?:\/[A-Za-z0-9-]+)?$/.test(route)){
  if(method==='POST')return ['사진을 로딩 중이에요','일기에 사진을 올리고 있어요.\n완료된 뒤 이동해 주세요.'];
  if(method==='DELETE')return ['사진을 삭제하고 있어요','선택한 사진을 삭제하고 있어요.\n완료된 뒤 이동해 주세요.'];
  return ['사진을 불러오고 있어요','일기에 담긴 사진을 불러오고 있어요.\n잠시 후 다시 이동해 주세요.'];
 }
 if(route.includes('/response_stream'))return ['답변을 준비하고 있어요','남겨주신 이야기를 읽고 답변하고 있어요.\n답변이 끝난 뒤 이동해 주세요.'];
 if(route.endsWith('/generate/diary'))return ['일기를 만들고 있어요','오늘의 이야기를 일기로 정리하고 있어요.\n일기가 완성된 뒤 이동해 주세요.'];
 if(route.endsWith('/messages')&&method==='POST')return ['대화를 보내고 있어요','입력하신 이야기를 보내고 있어요.\n전송이 끝난 뒤 이동해 주세요.'];
 if(route.includes('/diaries/')){
  if(method==='DELETE')return ['일기를 폐기하고 있어요','선택한 일기를 폐기하고 있어요.\n완료된 뒤 이동해 주세요.'];
  if(method==='POST'||method==='PATCH')return ['일기를 저장하고 있어요','일기 내용을 저장하고 있어요.\n저장이 끝난 뒤 이동해 주세요.'];
  return ['일기를 불러오고 있어요','일기 내용을 불러오고 있어요.\n잠시 후 다시 이동해 주세요.'];
 }
 return ['대화를 불러오고 있어요','저장된 대화를 화면에 불러오고 있어요.\n잠시 후 다시 이동해 주세요.'];
}

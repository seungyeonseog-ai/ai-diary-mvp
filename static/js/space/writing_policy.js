// 화면 상태와 무관하게 검사할 수 있는 읽기 시간·사진 제한 규칙.
export function replyReadingDelay(text){
 return Math.min(15000,Math.max(5000,[...text].length*65));
}
export const PHOTO_LIMIT=3;

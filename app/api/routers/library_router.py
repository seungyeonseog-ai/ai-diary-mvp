import logging
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy.orm import Session
from app.core.connection import get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.services import library_service

router=APIRouter(prefix='/library-data',tags=['library'])
logger=logging.getLogger(__name__)


def read(function,*args):
    try:return function(*args)
    except ValueError as error:raise HTTPException(422,str(error)) from None
    except Exception as error:
        logger.error('library_read_failed type=%s',type(error).__name__)
        raise HTTPException(503,'서재를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.') from None


@router.get('/shelf')
def shelf(page:int=Query(1,ge=1),db:Session=Depends(get_db),user=Depends(get_current_user)):
    return read(library_service.shelf,db,user.id,page)


@router.get('/month')
def month(month:str|None=Query(None,pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),page:int=Query(1,ge=1),
          db:Session=Depends(get_db),user=Depends(get_current_user)):
    return read(library_service.month_data,db,user.id,month,page)

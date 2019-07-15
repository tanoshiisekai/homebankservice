# -*-coding:utf-8-*-
#
# 本代码文件用于完成数据库操作
#

from flask import jsonify
from sqlalchemy import and_
from sqlalchemy import distinct
from appbase import global_db as db
from dbmodels.accountDBModel import Account
from dbmodels.summaryDBModel import Summary
from dbmodels.typeDBModel import AccountType
from dbmodels.userDBModel import User
from tools.info import Info
from tools.log import logger
from conf import perpage
from conf import datelength
from tools.decorator import checktoken
from tools.token import Token
from tools.timetools import datestrtomonth
from decimal import Decimal
from conf import exportpath
from conf import importpath
from tools.excel import writetofile
from conf import extvalid
from werkzeug.utils import secure_filename
from tools.excel import readfromfile
import os
import shutil
from tools.debug import r_set


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1] in extvalid


class AccountDAO:

    def __init__(self):
        pass

    @staticmethod
    def cleantempfiles():
        tokenlist = db.session.query(User.user_token).all()
        tokenlist = [x[0] for x in tokenlist if x[0]]
        filelist = os.listdir(exportpath)
        for f in filelist:
            if f not in tokenlist:
                shutil.rmtree(exportpath + "/" + f)
        filelist = os.listdir(importpath)
        for f in filelist:
            if f not in tokenlist:
                shutil.rmtree(importpath + "/" + f)



    @staticmethod
    @checktoken
    def importdata(user_token, file):
        summarylist = Summary.query.filter_by(summary_user=Token.getidbytoken(user_token)).all()
        accountlist = Account.query.filter_by(account_user=Token.getidbytoken(user_token)).all()
        for si in summarylist:
            db.session.delete(si)
        for ai in accountlist:
            db.session.delete(ai)
        file = file[0]
        if file and allowed_file(file.filename):
            filename = "temp.xls"
            if not os.path.exists(importpath + "/" + str(user_token)):
                os.mkdir(importpath + "/" + str(user_token))
            fileurl = importpath + "/" + str(user_token) + "/" + filename
            file.save(fileurl)
        if readfromfile(fileurl, Token.getidbytoken(user_token)):
            db.session.commit()
            return jsonify(Info(True, "数据导入成功！").tojson())
        else:
            return jsonify(Info(False, "数据导入失败！").tojson())

    @staticmethod
    @checktoken
    def exportdata(user_token):
        summarylist = db.session.query(
            Summary.summary_month, Summary.summary_out, Summary.summary_in,
            Summary.summary_lent, Summary.summary_borrow
        ).filter(Summary.summary_user == Token.getidbytoken(user_token)).all()
        writetofile("summarylist", summarylist, user_token)
        accountlist = db.session.query(
            Account.account_item, Account.account_money, Account.account_type,
            Account.account_date, Account.account_addition
        ).filter(Account.account_user == Token.getidbytoken(user_token)).all()
        if len(accountlist) == 0:
            return jsonify(Info(False, "无有效账目信息", None).tojson())
        writetofile("accountlist", accountlist, user_token)
        downloadurl = "/" + str(user_token) + "/data.xls"
        return jsonify(Info(True, "下载地址获取成功", downloadurl).tojson())

    @staticmethod
    @checktoken
    def getsummaryaccount(user_token):
        try:
            summarylist = db.session.query(
                Summary.summary_out,
                Summary.summary_in,
                Summary.summary_lent,
                Summary.summary_borrow,
                Summary.summary_in + Summary.summary_borrow - Summary.summary_out - Summary.summary_lent,
                Summary.summary_month).filter(
                Summary.summary_user == Token.getidbytoken(user_token)).all()
            totalaccount = sum([x[4] for x in summarylist])
            summarylist = [{"summary_total": x[4], "summary_month": x[5],
                            "summary_out": x[0], "summary_in": x[1],
                            "summary_lent": x[2], "summary_borrow": x[3]} for x in summarylist]
        except Exception as e:
            print(e)
            logger.error(e)
            return jsonify(Info(False, "数据库错误").tojson())
        else:
            return jsonify(Info(True, "汇总查询成功", [totalaccount, summarylist]).tojson())

    @staticmethod
    @checktoken
    def getborrowaccount(user_token):
        try:
            borrowlist = db.session.query(
                Account.account_id, Account.account_item,
                Account.account_money, Account.account_type,
                Account.account_date, Account.account_addition
                ).filter(and_(
                    Account.account_user == Token.getidbytoken(user_token),
                    Account.account_type == 4)).all()
            lentlist = db.session.query(
                Account.account_id, Account.account_item,
                Account.account_money, Account.account_type,
                Account.account_date, Account.account_addition
                ).filter(and_(
                    Account.account_user == Token.getidbytoken(user_token),
                    Account.account_type == 3)).all()
            accountlist = borrowlist + lentlist
        except Exception as e:
            print(e)
            logger.error(e)
            return jsonify(Info(False, "数据库错误").tojson())
        else:
            return jsonify(Info(True, "借贷查询成功", accountlist).tojson())

    @staticmethod
    @checktoken
    def removeaccount(user_token, params):
        account_id = params[0]
        account = Account.query.filter(and_(
            Account.account_id == account_id,
            Account.account_user == Token.getidbytoken(user_token))).first()
        db.session.delete(account)
        monthstr = datestrtomonth(account.account_date)
        summary = Summary.query.filter(
            Summary.summary_month == monthstr,
            Summary.summary_user == Token.getidbytoken(user_token)).first()
        if account.account_type == 1:
            summary.summary_out = summary.summary_out - account.account_money
        elif account.account_type == 2:
            summary.summary_in = summary.summary_in - account.account_money
        elif account.account_type == 3:
            summary.summary_lent = summary.summary_lent - account.account_money
        elif account.account_type == 4:
            summary.summary_borrow = summary.summary_borrow - account.account_money
        else:
            return jsonify(Info(False, "来源数据错误").tojson())
        try:
            db.session.commit()
        except Exception as e:
            print(e)
            logger.error(e)
            return jsonify(Info(False, "数据库错误").tojson())
        else:
            return jsonify(Info(True, "账目删除成功").tojson())

    @staticmethod
    @checktoken
    def getaccountbydatelength(user_token, params):
        page = params[0]
        datelist = db.session.query(distinct(Account.account_date)).order_by(Account.account_date.desc()).all()
        if len(datelist) % datelength == 0:
            pages = int(len(datelist) / datelength)
        else:
            pages = int(len(datelist) / datelength) + 1
        aimdatelist = datelist[(page - 1) * datelength:page * datelength]
        account = []
        try:
            for aimdate in aimdatelist:
                accounttemp = db.session.query(
                    Account.account_id, Account.account_item,
                    Account.account_money, Account.account_type,
                    Account.account_date, Account.account_addition).filter(and_(
                        Account.account_user == Token.getidbytoken(user_token),
                        Account.account_date == aimdate[0])).all()
                account.extend(accounttemp)
        except Exception as e:
            print(e)
            logger.error(e)
            return jsonify(Info(False, "数据库错误").tojson())
        else:
            return jsonify(Info(True, pages, account).tojson())

    @staticmethod
    @checktoken
    def getaccountbypage(user_token, params):
        page = params[0]
        try:
            allitems = db.session.query(Account).filter(
                Account.account_user == Token.getidbytoken(user_token)).count()
            if allitems % perpage == 0:
                pages = int(allitems / perpage)
            else:
                pages = int(allitems / perpage) + 1
            account = db.session.query(
                Account.account_id, Account.account_item,
                Account.account_money, Account.account_type,
                Account.account_date, Account.account_addition).filter(
                Account.account_user == Token.getidbytoken(user_token)).order_by(
                Account.account_date.desc()).offset(
                (page-1)*perpage).limit(perpage).all()
        except Exception as e:
            print(e)
            logger.error(e)
            return jsonify(Info(False, "数据库错误").tojson())
        else:
            return jsonify(Info(True, pages, account).tojson())

    @staticmethod
    @checktoken
    def addaccount(user_token, params):
        account = params[0]
        account_item = account["account_item"]
        account_money = Decimal(account["account_money"])
        account_type = int(account["account_type"])
        account_date = account["account_date"]
        account_addition = account["account_addition"]
        account_user = Token.getidbytoken(user_token)
        account = Account(
            account_item, account_money, account_type, account_date, account_addition, account_user)
        db.session.add(account)
        monthstr = datestrtomonth(account_date)
        if Summary.query.filter(
                and_(Summary.summary_month == monthstr,
                     Summary.summary_user == Token.getidbytoken(user_token))).count() == 0:
            db.session.add(Summary(monthstr, 0, 0, 0, 0, Token.getidbytoken(user_token)))
        summary = Summary.query.filter(
            Summary.summary_month == monthstr,
            Summary.summary_user == Token.getidbytoken(user_token)).first()
        if account_type == 1:
            summary.summary_out = summary.summary_out + account_money
        elif account_type == 2:
            summary.summary_in = summary.summary_in + account_money
        elif account_type == 3:
            summary.summary_lent = summary.summary_lent + account_money
        elif account_type == 4:
            summary.summary_borrow = summary.summary_borrow + account_money
        else:
            return jsonify(Info(False, "来源数据错误").tojson())
        try:
            db.session.commit()
        except Exception as e:
            print(e)
            logger.error(e)
            return jsonify(Info(False, "账目添加失败，数据库错误").tojson())
        else:
            return jsonify(Info(True, "账目添加成功").tojson())

#!/usr/bin/env python
# -*- coding: utf-8 -*-

import abc
import datetime
import hashlib
import json
import logging
import uuid
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from optparse import OptionParser
from weakref import WeakKeyDictionary

SALT = "Otus"
ADMIN_LOGIN = "admin"
ADMIN_SALT = "42"
OK = 200
BAD_REQUEST = 400
FORBIDDEN = 403
NOT_FOUND = 404
INVALID_REQUEST = 422
INTERNAL_ERROR = 500
ERRORS = {
    BAD_REQUEST: "Bad Request",
    FORBIDDEN: "Forbidden",
    NOT_FOUND: "Not Found",
    INVALID_REQUEST: "Invalid Request",
    INTERNAL_ERROR: "Internal Server Error",
}
UNKNOWN = 0
MALE = 1
FEMALE = 2
GENDERS = {
    UNKNOWN: "unknown",
    MALE: "male",
    FEMALE: "female",
}


class BaseField(object):
    def __init__(self, required=True, nullable=False):
        self.required = required
        self.nullable = nullable
        self.data = WeakKeyDictionary()

    def __get__(self, instance, cls):
        return self.data.get(instance)

    def __set__(self, instance, value):
        self.data[instance] = value


class ArgumentsField(BaseField):
    def __set__(self, instance, value):
        try:
            json_obj = json.loads(json.dumps(value))
        except ValueError:
            raise TypeError("{} is not a valid json".format(str(value)))

        super(BaseField, self).__set__(instance, value)


class CharField(BaseField):
    def check(self, value):
        if not isinstance(value, str):
            raise TypeError('{} is not a str'.format(value))

    def __set__(self, instance, value):
        self.check(value)
        super(CharField, self).__set__(instance, value)


class EmailField(CharField):
    EMAIL_PATTERN = r'^[a-z][\w\-\.]*@([a-z][\w\-]+\.)+[a-z]{2,4}$'

    def check(self, value):
        super(EmailField, self).check(value)

        if not re.match(self.EMAIL_PATTERN, value):
            raise TypeError('{} is not a valid email'.format(value))

    def __set__(self, instance, value):
        self.check(value)
        super(CharField, self).__set__(instance, value)


class PhoneField(BaseField):
    PHONE_PATTERN = r'^\d+$'

    def __set__(self, instance, value):
        if not re.match(self.EMAIL_PATTERN, value):
            raise TypeError('{} is not a valid phone'.format(value))
        super(BaseField, self).__set__(instance, value)


class DateField(BaseField):
    DATE_PATTERN = r'^\d{2}\.\d{2}\.\d{4}$'

    @staticmethod
    def get_date(self, value):
        return datetime.strptime(value, '%d.%m.%Y')

    def check(self, value):
        if not (isinstance(value, str) & re.match(self.DATE_PATTERN)):
            raise TypeError('{} is not a valid date'.format(value))

    def __set__(self, instance, value):
        self.check(value)
        super(BaseField, self).__set__(instance, self.get_date(value))


class BirthDayField(DateField):
    def check(self, value):
        super(BirthDayField, self).check(value)

        if int(re.split(r'[\.]', value)[2]) < datetime.now().year:
            raise ValueError('{} is more than 70 years ago'.format(value))

    def __set__(self, instance, value):
        self.check(value)
        super(BaseField, self).__set__(instance, self.get_date(value))


class GenderField(BaseField):
    def __set__(self, instance, value):
        if not (isinstance(value, int) & int(value) in (UNKNOWN, MALE, FEMALE)):
            raise TypeError('{} is not a valid gender'.format(value))
        super(CharField, self).__set__(instance, value)


class ClientIDsField(BaseField):
    def __set__(self, instance, value):
        if not isinstance(value, list):
            raise TypeError('{} is not a list'.format(value))
        super(BaseField, self).__set__(instance, value)


class BaseRequest(metaclass=abc.ABCMeta):
    @classmethod
    @abc.abstractmethod
    def from_dict(cls, arguments):
        raise NotImplementedError

    @abc.abstractmethod
    def process_request(self):
        raise NotImplementedError


class ClientsInterestsRequest(BaseRequest):
    client_ids = ClientIDsField(required=True)
    date = DateField(required=False, nullable=True)

    def from_dict(cls, arguments):
        pass

    def process_request(self):
        pass


class OnlineScoreRequest(BaseRequest):
    first_name = CharField(required=False, nullable=True)
    last_name = CharField(required=False, nullable=True)
    email = EmailField(required=False, nullable=True)
    phone = PhoneField(required=False, nullable=True)
    birthday = BirthDayField(required=False, nullable=True)
    gender = GenderField(required=False, nullable=True)

    def from_dict(cls, arguments):
        pass

    def process_request(self):
        pass


class MethodRequest(object):
    account = CharField(required=False, nullable=True)
    login = CharField(required=True, nullable=True)
    token = CharField(required=True, nullable=True)
    arguments = ArgumentsField(required=True, nullable=True)
    method = CharField(required=True, nullable=False)

    @property
    def is_admin(self):
        return self.login == ADMIN_LOGIN

    @classmethod
    def from_request(cls, request):
        try:
            request_dict = json.loads(json.dumps(request['body']))

            self = cls()
            self.account = request_dict['account']
            self.login = request_dict['login']
            self.token = request_dict['token']
            self.arguments = request_dict['arguments']

            return self
        except Exception:
            return None

    def process_request(self):
        try:
            if self.method.upper() == 'ONLINE_SCORE':
                request = OnlineScoreRequest().fromdict(self.arguments)
            elif self.method.upper() == 'CLIENTS_INTERESTS':
                request = ClientsInterestsRequest().fromdict(self.arguments)
            else:
                return ERRORS[INVALID_REQUEST], INVALID_REQUEST

        except Exception:
            return ERRORS[INVALID_REQUEST], INVALID_REQUEST

        return request.process_request()


def check_auth(request):
    sha512 = hashlib.sha512()
    if request.is_admin:
        sha512.update((datetime.datetime.now().strftime("%Y%m%d%H") + ADMIN_SALT).encode('UTF-8'))
    else:
        sha512.update((request.account + request.login + SALT).encode('UTF-8'))

    digest = sha512.hexdigest()
    if digest == request.token:
        return True
    return False


def method_handler(request, ctx, store):
    method_request = MethodRequest().from_request(request)
    if not method_request:
        return ERRORS[INVALID_REQUEST], INVALID_REQUEST

    if not check_auth(method_request):
        return ERRORS[FORBIDDEN], FORBIDDEN

    return method_request.process_request()


class MainHTTPHandler(BaseHTTPRequestHandler):
    router = {
        "method": method_handler
    }
    store = None

    def get_request_id(self, headers):
        return headers.get('HTTP_X_REQUEST_ID', uuid.uuid4().hex)

    def do_POST(self):
        response, code = {}, OK
        context = {"request_id": self.get_request_id(self.headers)}
        request = None
        try:
            data_string = self.rfile.read(int(self.headers['Content-Length']))
            request = json.loads(data_string)
        except:
            code = BAD_REQUEST

        if request:
            path = self.path.strip("/")
            logging.info("%s: %s %s" % (self.path, data_string, context["request_id"]))
            if path in self.router:
                try:
                    response, code = self.router[path]({"body": request, "headers": self.headers}, context, self.store)
                except Exception as e:
                    logging.exception("Unexpected error: %s" % e)
                    code = INTERNAL_ERROR
            else:
                code = NOT_FOUND

        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if code not in ERRORS:
            r = {"response": response, "code": code}
        else:
            r = {"error": response or ERRORS.get(code, "Unknown Error"), "code": code}
        context.update(r)
        logging.info(context)
        self.wfile.write(json.dumps(r))
        return


if __name__ == "__main__":
    op = OptionParser()
    op.add_option("-p", "--port", action="store", type=int, default=8080)
    op.add_option("-l", "--log", action="store", default=None)
    (opts, args) = op.parse_args()
    logging.basicConfig(filename=opts.log, level=logging.INFO,
                        format='[%(asctime)s] %(levelname).1s %(message)s', datefmt='%Y.%m.%d %H:%M:%S')
    server = HTTPServer(("localhost", opts.port), MainHTTPHandler)
    logging.info("Starting server at %s" % opts.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()

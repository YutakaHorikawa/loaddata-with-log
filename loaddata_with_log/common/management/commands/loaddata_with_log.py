# -*- coding:utf-8 -*-
import datetime
from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.core import management
from optparse import make_option
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.contenttypes.models import ContentType
from django.utils.encoding import force_unicode
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import signals
from django.contrib.auth import authenticate
LOADDATA = 10

class Command(BaseCommand):
    """
    loaddataの拡張コマンド。
    loddataした時間や変更個所をMySQL(django_admin_logテーブル)に残してくれる。
    usernameとpasswordはadminのものを使用してください。
    python ./manage.py loaddata_with_log ./masterdata/json/aaa.json --username admin --password admin --app appname --class ModelClass
    """
    
    def init(self):
        self.old_datas = None
        self.old_ids = None
        self.Klass = None

    option_list = BaseCommand.option_list + (
        make_option('--username', action='store', dest='username', default=None,
            help='username.'),
        make_option('--password', action='store', dest='password', default=None,
            help='password.'),
        make_option('--app', action='store', dest='app', default=None,
            help='model.'),
        make_option('--class', action='store', dest='class', default=None,
            help='model.'),
        make_option('--all', action='store', dest='all', default=None,
            help='all.'),
    )
    help = 'Installs the named fixture(s) in the database with logging.'
    args = "fixture [fixture ...] --username xxx --password xxx --module xxx --model xxx"

    def command_exit(self, msg):
        print u"Error: %s" % msg
        exit()

    def _value_check(self, old_data, new_data):
        """
        値のチェック
        値が更新されていたり、カラムの増減があったらメッセージを返す
        """
        
        def get_dict_value(key, data):
            try:
                value = data.__dict__['%s' % key]
            except KeyError:
                return None, False
            
            return value, True
        
        messages = []
        keys = new_data.__dict__.keys()
        for key in keys:
            #_stateは無視
            if key != '_state':
                message = ''
                old_value, old_result = get_dict_value(key, old_data)
                new_value, new_result = get_dict_value(key, new_data)
                
                #カラムが新しく追加
                if old_result is False:
                    message = u'%sカラムが追加。 value:%s' % (key, new_value)

                #値が更新されている!
                if old_value != new_value:
                    message = u'%sの値が変更: %s → %s' % (key, old_value, new_value)
                
                if message:
                    messages.append(message)
        
        return messages
    
    def _make_new_recode_message(self):
        pass

    def _search_list(self, target_list, instance):
        if not instance:
            return False, None
        count = 0
        instance_id = int(instance.pk)
        data_list = list(self.old_datas)
        while(1):
            
            if not target_list:
                return False, None, None
            
            if len(target_list) == 1:
                search_index = 0
            else:
                search_index = int(len(target_list) / 2)

            try:
                target_id = target_list[search_index - 1]
            except IndexError:
                return False, None, None
            
            #同じ値を発見!
            if instance_id == int(target_id) and len(target_list) > 1:
                return True, data_list[search_index - 1], target_id
            elif instance_id != int(target_id) and len(target_list) == 1:
                return True, None, target_id
            elif instance_id == int(target_id) and len(target_list) == 1:
                return True, data_list[search_index - 1], target_id

            if target_id < instance_id:
                target_list = target_list[search_index -1 + 1:]
                data_list = data_list[search_index - 1 + 1:]
            elif target_id > instance_id:
                target_list = target_list[:search_index - 1]
                data_list = data_list[:search_index - 1]
            
    def _make_change_message_text(self, instance):
        msg = ''
        if not self.old_datas:
            return u'新規作成'
        
        def make_message(messages):
            return_message = ''
            for message in messages:
                return_message = return_message + message + '\r'
            return return_message
        
        result, data, id = self._search_list(list(self.old_ids), instance)
        
        if result and data:
            messages = self._value_check(data, instance)
            
            if not messages:
                return u'更新無し'
            return make_message(messages)
        if result and not data:
            return u'レコード追加'
        
        return u'更新無し'

    def _impot_class(self, module_name, class_name):
        """
        クラスをインポート
        """
        
        try:
            module = __import__(module_name, globals(), locals(), [class_name], -1)
            Klass = getattr(module, class_name)
        except ImportError, e:
            self.command_exit('Error ImportError')
        except Exception, e:
            self.command_exit('Error')
        
        return Klass
    
    
    def handle(self, *fixture_labels, **options):
        a = datetime.datetime.now()
        user = authenticate(username=options.get('username'), password=options.get('password'))
        app = options.get('app')
        class_name = options.get('class')
        
        if not user or not app or not class_name:
            self.command_exit('Dameeeee1')
        
        if user is not None and user.is_authenticated():
            
            self.init()#変数を初期化
            
            module_name = 'kaizoku.%s.models' % app
            Klass = self._impot_class(module_name, class_name)
            self.Klass = Klass
            #更新前のデータを取得
            self.old_datas = list(Klass.objects.all())
            self.old_ids = list([data.pk for data in self.old_datas])
            self.old_ids.sort()
            def add_log_data(instance, raw, created, **kwargs):
                #更新箇所を知らせるテキストを作成する
                change_message_text = self._make_change_message_text(instance)
                LogEntry.objects.log_action(
                    user_id         = user.pk, 
                    content_type_id = ContentType.objects.get_for_model(instance).pk,
                    object_id       = instance.pk,
                    object_repr     = force_unicode(instance), 
                    change_message  = change_message_text,
                    action_flag     = ADDITION + LOADDATA if created else CHANGE + LOADDATA
                )
            signals.post_save.connect(add_log_data, sender=Klass)
            management.call_command('loaddata', *fixture_labels, **options)
            b = datetime.datetime.now()
            print b - a
        else:
            print 'Authenticate failed.'

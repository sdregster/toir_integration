import os
from typing import Sequence
import xml.etree.ElementTree as ElementTree
import xmltodict
from domain import entities
from .. import xml_file, serializers


class GetNewDataAdapter:
    # часть имени файла, который содержит данные об объектах ремонта
    XML_FILE = 'ВыгрузкаДанныхОР'
    # переменная для сохранения справочников dict like {attribute_name: {toir_id: {value: value, parent: parent}}}
    REFERENCE_ATTRIBUTES_VALUES = {}

    OBJECTS = [
        'operation_object',
        'equipment',
        'tech_position',
        'object_repair_group',
        'property',
        'plan_repair',
        'fact_repair',
        'failure',
        'part',
    ]

    def __init__(self, file_directory):
        """
        Конструктор для адаптера.
        :param file_directory: путь к директории с файлами выгрузками xml с завершающим слэшем.
        Например //irkoil/ТОиР_Неосинтез/
        """
        self._file_directory = file_directory
        self._elements_all = None

    def _get_file_path(self, name: str) -> str:
        """
        Метод для получения полного пути файла на основе части имени файла. В случае если файл не найден
        поднимает исключение. Если файлов несколько, то возвращает последний (с наибольшей датой создания)
        :param name: часть имени файла в виде строки.
        :return: абсолютный путь к конкретному файлу
        """
        f_list = [f for f in os.listdir(path=self._file_directory) if name in f and '~' not in f]
        if f_list:
            f_date = [os.path.getctime(self._file_directory + f) for f in f_list]
            file_path = self._file_directory + f_list[f_date.index(max(f_date))]
        else:
            raise FileNotFoundError()
        return file_path

    @property
    def _elements(self) -> dict[str, list]:
        """
        Свойство. При первом вызове выполняет чтение файла
        :return: dict like {'parent toir id': [elements]}
        """
        # если данные уже ранее прочитаны, то просто вернуть их
        if self._elements_all:
            return self._elements_all
        # чтение файла и получение данных в виде итератора по всем элементам (тегам) в xml файле
        xml_iterator = ElementTree.iterparse(self._get_file_path(self.XML_FILE))
        elements_hash_table = {}
        # итерация по всем элементов в итераторе
        for _, element in xml_iterator:
            # если тег содержит ДанныеОР - это элемент содержащий все данные по конкретному объекту ремонта
            # для получения dict {'parent toir id': [elements]} по каждому элементу извлекается идентификатор
            # объекта-родителя и сам элемент складывается в значение соответствующего ключа
            if 'ДанныеОР_' in element.tag:
                parent = element.find('РеквизитыОР/ОбъектРемонта_Родитель').text
                if parent in elements_hash_table:
                    elements_hash_table[parent].append(element)
                else:
                    elements_hash_table[parent] = [element]
        # сохранить прочитанные данные в переменную, чтобы не читать повторно
        self._elements_all = elements_hash_table
        return self._elements_all

    def retrieve(self, operation_object: entities.OperationObject, retrievable_object: str) -> Sequence:
        serializer = serializers.get_serializer(retrievable_object)
        if operation_object:
            xml_elements = xml_file.GetElementsByParent(self._elements).execute(operation_object.toir_id,
                                                                                retrievable_object)
            items = list()
            for element in xml_elements:
                item = serializer.init_from_xml(element)
                item.object_id = operation_object.object_id
                items.append(item)

                self._get_nested_objects(item, element)

        else:
            file = serializer.file
            data = self._get_dimensions_data_from_file(file)
            items = [serializer.init_from_dict(item) for item in data]

        return items

    @staticmethod
    def _get_nested_objects(item, host_element):
        nested_objects = [
            {'nested_object': 'property', 'attribute_name': 'properties'},
            {'nested_object': 'plan_repair', 'attribute_name': 'plan_repairs'},
            {'nested_object': 'fact_repair', 'attribute_name': 'fact_repairs'},
            {'nested_object': 'failure', 'attribute_name': 'failures'},
            {'nested_object': 'part', 'attribute_name': 'parts'},
        ]
        for nested_object in nested_objects:
            retrievable_nested_object = nested_object['nested_object']
            attribute_name = nested_object['attribute_name']
            if hasattr(item, attribute_name):
                serializer = serializers.get_serializer(retrievable_nested_object)
                data = host_element.find(serializer.tag)
                xml_elements = []
                element = None
                for child in data:
                    if child.tag == 'ОР':
                        element = ElementTree.Element(serializer.tag)
                        xml_elements.append(element)
                    # add child only if it has value
                    if element is not None and child.text is not None:
                        element.append(child)
                # do not serialize empty objects
                xml_elements = list(filter(lambda x: len(x) > 1, xml_elements))
                item_nested_objects = [serializer.init_from_xml(one) for one in xml_elements]
                if item_nested_objects:
                    setattr(item, attribute_name, item_nested_objects)

    def _get_dimensions_data_from_file(self, file_name) -> list[dict]:
        with open(self._get_file_path(file_name), encoding='UTF-8') as fd:
            doc = xmltodict.parse(fd.read())

        headers = []
        for column in doc['ValueTable']['column']:
            headers.append(column['Title'])

        rows = []
        for row in doc['ValueTable']['row']:
            values = []
            for value in row['Value']:
                value_text = value['#text'] if value['@xsi:type'] != 'Null' else None
                values.append(value_text)
            rows.append(values)

        return list(map(lambda x: dict(zip(headers, x)), rows))

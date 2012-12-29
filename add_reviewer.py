import sys, json
from pipes import quote
import subprocess
import pywikibot
import lxml.objectify
import re

import sys
sys.path.append('python-gerrit')
from gerrit.rpc import Client; g=Client('https://gerrit.wikimedia.org/r/');

site = pywikibot.getSite('mediawiki', 'mediawiki')

class ReviewerFactory(object):
    nofilere = re.compile('')

    def __init__(self, site=pywikibot.getSite('mediawiki', 'mediawiki'),
                       page="Git/Reviewers",
                       template="Gerrit-reviewer"):
        self.site = site
        self.page = page
        self.template = template

    @property
    def data(self):
        if hasattr(self, '_data'):
            return self._data
        return pywikibot.data.api.Request(action="parse", page=self.page, generatexml=True, site=self.site).submit()

    @property
    def objecttree(self):
        return lxml.objectify.fromstring(self.data['parse']['parsetree']['*'])

    def _tryParseInt(self, value, default=None):
        try:
            return int(value)
        except Exception, e:
            return default

    def reviewer_generator(self, project, changedfiles):
        tree = self.objecttree

        for section in tree.iter('h'):
            if section.text.strip('= ') != project:
                continue
            for sibling in section.itersiblings():
                if sibling.tag == "h":
                    break
                if sibling.tag == "template" and sibling.title == self.template:
                    reviewer = None; modulo = 1; filere=self.nofilere
                    for part in sibling.iter('part'):
                        if part.name == "" and part.name.attrib['index'] == '1':
                            reviewer = part.value.text
                        elif part.name == "every":
                            modulo = self._tryParseInt(part.value, 1)
                            if modulo < 2:
                                modulo = 1
                        elif part.name == "file_regexp":
                            filere = re.compile(part.value.text or part.value.ext.inner.text, flags=re.DOTALL | re.IGNORECASE)
                    if any(filere.match(file) for file in changedfiles):
                        yield reviewer, modulo


def get_reviewers(change, RF=ReviewerFactory()):
    try:
        num = int(change['number'])
        reviewers = []
        try:
            changedfiles = [p.path for p in g.change_details(num).last_patchset_details.patches]
        except Exception, e:
            print e
            changedfiles = []
        for i, (reviewer, modulo) in enumerate(RF.reviewer_generator(change['project'], changedfiles)):
            if ((num + i) % modulo == 0):
                reviewers.append(reviewer)
        return reviewers
    except Exception, e:
        print e
        return []

def test_get_reviewers():
    RF = ReviewerFactory()
    RF._data = json.load(open("api_result"))
    name = 'test/mediawiki/extensions/examples'

    for i in [40978, 40976, 40975]:
        change = {'number': i, 'project': name}
        revs = get_reviewers(change, RF)
        for rev in revs:
            assert isinstance(rev, str)
        if i % 5 == 0:
            assert revs == ["Merlijn van Deen", "Sumanah"]
        else:
            assert revs == ["Sumanah"]

    RF = ReviewerFactory()
    for i in [40978, 40976, 40975, 34673]:
        change = {'number': i, 'project': name}
        revs = get_reviewers(change, RF)
        print name, i, revs

if __name__ == "__main__":
    while True:
        line = sys.stdin.readline()
        data = json.loads(line)
        if data['type'] != 'patchset-created':
            continue
        change = data['change']
        patchset = data['patchSet']
        if int(patchset['number']) != 1:
            continue
        if change['owner']['name'] == 'L10n-bot':
            print "Skipping L10n patchset ", change['number']
            continue

        reviewers = get_reviewers(change)

        if reviewers:
            params = []
            for reviewer in reviewers:
                params.append('--add')
                params.append(reviewer)
            params.append(change['id'])
            command = "gerrit set-reviewers " + " ".join(quote(p) for p in params)
            print command
            print subprocess.call(["ssh", "-i", "id_rsa", "-p", "29418", "reviewer-bot@gerrit.wikimedia.org", command])

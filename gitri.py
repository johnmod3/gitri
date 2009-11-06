import os
import shutil
import sys
import tempfile
import xml.dom.minidom

import git

class GitriError(StandardError):
	pass

class InvalidProjectError(GitriError):
	pass

GITRI_DIR = '.gitri'

class Project(object):
	def __init__(self, dir):
		self.dir = os.path.abspath(dir)
		if not self.valid_project(self.dir):
			raise InvalidProjectError('not a valid gitri project')

		self.gitri_dir = os.path.join(self.dir, GITRI_DIR)
		manifest_dir = os.path.join(self.gitri_dir, 'manifest')
		if git.Repo.valid_repo(manifest_dir):
			self.manifest_repo = git.Repo(manifest_dir)
		else:
			self.manifest_repo = None

		self.remotes = {}
		self.repos = []
		self.default = {}

		manifest = xml.dom.minidom.parse(os.path.join(self.gitri_dir, 'manifest.xml'))
		m = manifest.childNodes[0]
		if m.localName != 'manifest':
			raise GitriError('malformed manifext.xml: no manifest element')
		for node in m.childNodes:
			if node.localName == 'default':
				self.default.update(dict(node.attributes.items()))
			elif node.localName == 'remote':
				remote = dict(node.attributes.items())
				#TODO: detect duplicates
				self.remotes[remote['name']] = remote
			elif (node.localName == 'project') or (node.localName == 'repo'):
				repo = {}
				repo.update(self.default)
				repo.update(dict(node.attributes.items()))
				#TODO: detect duplicates
				self.repos.append(repo)

	@classmethod
	def find_project(cls, dir = None):
		if dir == None:
			dir = os.getcwd()

		head = dir
		while head:
			try:
				return cls(head)
			except InvalidProjectError:
				if head == '/':
					head = None
				else:
					(head, tail) = os.path.split(head)

		raise InvalidProjectError('not a valid gitri project')

	@classmethod
	def init(cls, url, dir=None, revset=None):
		if dir == None:
			#TODO: come up with a better default name, if possible
			dir = os.path.splitext(os.path.basename(url))[0]
		dir = os.path.abspath(dir)

		if os.path.exists(dir):
			raise GitriError('Directory already exists')

		if revset:
			git.Repo.clone(url, dir=os.path.join(dir, GITRI_DIR, 'manifest'), rev=revset)
		else:
			git.Repo.clone(url, dir=os.path.join(dir, GITRI_DIR, 'manifest'))

		manifest_src = os.path.join(dir, GITRI_DIR, 'manifest', 'default.xml')
		if not os.path.exists(manifest_src):
			GitriError('invalid manifest repo: no default.xml')

		#TODO:{c,sh}ouldn't this be a symlink?
		shutil.copy(manifest_src, os.path.join(dir, GITRI_DIR, 'manifest.xml'))

		p = cls(dir)
		p.sync()

	@classmethod
	def valid_project(cls, dir):
		return os.path.exists(os.path.join(dir, GITRI_DIR, 'manifest.xml'))

	def revset(self):
		return self.manifest_repo.head()

	def origin(self):
		return 'origin'

	def sync(self):
		for r in self.repos:
			path = os.path.abspath(os.path.join(self.dir, r['path']))
			print r['name']
			gitri_branch = 'gitri/%s/%s' % (self.origin(), self.revset())
			bookmark_branch = 'refs/bookmarks/%s/%s' % (self.origin(), self.revset())

			if git.Repo.valid_repo(path):
				repo = git.Repo(path)
				repo.fetch(r['remote'])
				repo.remote_set_head(r['remote'])
				remote_branch = '%s/%s' % (r['remote'], r.get('revision', 'HEAD'))
				#Make sure we're on the right branch
				if repo.head() != gitri_branch:
					print '%s has changed branches and cannot be safely synced. Skipping this repo.' % r['name']
				#Fast-Forward if we can
				elif repo.can_fastforward(remote_branch):
					repo.merge(remote_branch)
				#otherwise rebase local work
				elif repo.is_descendant(bookmark_branch):
					if repo.dirty():
						print '%s has local changes and cannot be rebased. Skipping this repo.' % r['name']
					repo.rebase(bookmark_branch, onto=remote_branch)
			else:
				url = self.remotes[r['remote']]['fetch'] + '/' + r['name']
				if r.has_key('revision'):
					repo = git.Repo.clone(url, dir=path, remote=r['remote'], rev=r['revision'], local_branch=gitri_branch)
				else:
					repo = git.Repo.clone(url, dir=path, remote=r['remote'], local_branch=gitri_branch)

			repo.update_ref(bookmark_branch, 'HEAD')

gitri_commands = {
	'init': (Project.init, False),
	'sync': (Project.sync, True),
	}

if __name__ == '__main__':
	if (len(sys.argv) < 2) or not gitri_commands.has_key(sys.argv[1]):
		#TODO: write usage
		print 'gitri usage'
	else:
		cmd = gitri_commands[sys.argv[1]]
		if cmd[1]:
			cmd[0](Project.find_project(), *sys.argv[2:])
		else:
			cmd[0](*sys.argv[2:])

#The following code was necessary before manual clone was implemented in order to
#clone into a non-empty directory
#if os.path.exists(path) and (not os.path.isdir(path)):
#	GitriError('path %s already exists and is not a directory' % (path,))
#elif os.path.isdir(path) and (os.listdir(path) != []):
#	tmp_path = tempfile(dir='.')
#	#todo: proper path join (detect foreign OS)
#	repo = git.Repo.clone(self.remotes[p['remote']]['fetch'] + '/' + p['name'], tmp_path)
#	#move tmp_path to path
#	#rmdir tmp_path
#else:
#	#path is an empty directory, or doesn't exist
#	#todo: proper path join (detect foreign OS)

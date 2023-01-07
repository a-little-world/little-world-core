.. Little World Documentation master file, created by
   tbcode on Tue Oct 25 16:11:00 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Little World Documentation
==================================

General documentation of all little world software components.
This includes full code documentation for the backend.
Documentation for build and development tools for both back and frontends.

The Backend
==================================

Heart of little world are script services database models and apis that make little world work.
The backend repository contains general build tools and several django applications for the backend.
There are severl external subrepositories that are also managed by us, see :doc:`backend_repo_submodules`

* for getting started on backend development visit the :doc:`getting_started_backend` page
* for building translations visit the :doc:`backend_making_translations`
* for a overview of the main django applications visit :doc:`modules`

Here you can search the code documentation of the backend :ref:`search`

The Frontends
==================================

Little world frontend is build up by several react applications:

* The main frontend is the little world web app containing chat, video calls help screens etc.
* The user form contains views for login registration and the matching form
* The admin frontend contains views for admin users to manage users, make matches and provide support

* for general getting started on frontend development visit the :doc:`getting_started_frontend` page


.. raw:: html

   <details>
   <summary><a>Full toc tree</a></summary>

.. toctree::
   getting_started_backend.md
   getting_started_frontend.md
   apidoc/run.rst
   modules.rst

.. raw:: html

   </details>
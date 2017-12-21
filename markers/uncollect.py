"""
uncollect
---------

Used internally to mark a test to be "uncollected"

This mark should be used at any point before or during test collection to
dynamically flag a test to be removed from the list of collected tests.

py.test adds marks to test items a few different ways. When marking in a py.test
hook that takes an ``Item`` or :py:class:`Node <pytest:_pytest.main.Node>` (``Item``
is a subclass of ``Node``), use ``item.add_marker('uncollect')`` or
``item.add_marker(pytest.mark.uncollect)``

When dealing with the test function directly, using the mark decorator is preferred.
In this case, either decorate a test function directly (and have a good argument ready
for adding a test that won't run...), e.g. ``@pytest.mark.uncollect`` before the test
``def``, or instantiate the mark decorator and use it to wrap a test function, e.g.
``pytest.mark.uncollect()(test_function)``


uncollectif
-----------

The ``uncollectif`` marker is very special and can cause harm to innocent kittens if used
incorrectly. The ``uncollectif`` marker enables the ability to uncollect a specific test
if a certain condition is evaluated to ``True``. The following is an example:


    .. code-block:: python

        @pytest.mark.uncollectif(lambda: version.current_version() < '5.3')

In this case, when pytest runs the modify items hook, it will evaluate the lambda function
and if it results in ``True``, then the test will be uncollected. Fixtures that are
generated by testgen, such as provider_key, provider_data etc, are also usable inside
the ``collectif`` marker, assuming the fixture name is also a prerequisite for the test
itself. For example:: python

    .. code-block:: python

        @pytest.mark.uncollectif(lambda provider_type: provider_type != 'virtualcenter')
        def test_delete_all_snapshots(test_vm, provider_key, provider_type):
            pass

Here, the fixture provider_type is special as it comes from testgen and is passed to the
lambda for comparison.

Note:
    Be aware, that this cannot be used for any other fixture types. Doing so will break
    pytest and may invalidate your puppies.

"""
import inspect
import pytest

MARKDECORATOR_TYPE = type(pytest.mark.slip)


# work around https://github.com/pytest-dev/pytest/issues/2400
def get_uncollect_function(marker_or_markdecorator):
    if isinstance(marker_or_markdecorator, MARKDECORATOR_TYPE):
        return marker_or_markdecorator.args[0]
    else:
        return list(marker_or_markdecorator)[0].args[0]


def uncollectif(item):
    """ Evaluates if an item should be uncollected

    Tests markers against a supplied lambda from the marker object to determine
    if the item should be uncollected or not.
    """

    from cfme.utils.pytest_shortcuts import extract_fixtures_values
    marker = item.get_marker('uncollectif')
    if marker:
        from cfme.utils.log import logger
        log_msg = 'Trying uncollecting {}: {}'.format(
            item.name,
            marker.kwargs.get('reason', 'No reason given'))

        try:
            arg_names = inspect.getargspec(get_uncollect_function(marker)).args
        except TypeError:
            logger.debug(log_msg)
            return not bool(marker.args[0])

        holder = item.config.pluginmanager.getplugin('appliance-holder')
        if holder:
            global_vars = {'appliance': holder.held_appliance}
        else:
            logger.info("while uncollecting %s - appliance not known", item)
            global_vars = {}

        try:
            values = extract_fixtures_values(item)
            values.update(global_vars)
            # The test has already been uncollected
            if arg_names and not values:
                return
            args = [values[arg] for arg in arg_names]
        except KeyError:
            missing_argnames = list(set(arg_names) - set(item._request.funcargnames))
            func_name = item.name
            if missing_argnames:
                raise Exception("You asked for a fixture which wasn't in the function {} "
                                "prototype {}".format(func_name, missing_argnames))
            else:
                raise Exception("Failed to uncollect {}, best guess a fixture wasn't "
                                "ready".format(func_name))
        retval = marker.args[0](*args)
        if retval:
            logger.debug(log_msg)
        return not retval
    else:
        return True


def pytest_collection_modifyitems(session, config, items):
    from fixtures.pytest_store import store
    len_collected = len(items)

    new_items = []

    from cfme.utils.path import log_path
    with log_path.join('uncollected.log').open('w') as f:
        for item in items:
            # First filter out all items who have the uncollect mark
            if item.get_marker('uncollect') or not uncollectif(item):
                # if a uncollect marker has been added,
                # give it priority for the explanation
                uncollect = item.get_marker('uncollect')
                marker = uncollect or item.get_marker('uncollectif')
                if marker:
                    reason = marker.kwargs.get('reason', "No reason given")
                else:
                    reason = None
                f.write("{} - {}\n".format(item.name, reason))
            else:
                new_items.append(item)

    items[:] = new_items

    len_filtered = len(items)
    filtered_count = len_collected - len_filtered
    store.uncollection_stats['uncollectif'] = filtered_count
